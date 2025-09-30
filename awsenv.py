import argparse
from datetime import datetime, timezone
import json
import os
import pyotp
import shlex
import shutil
import subprocess
import sys
import tempfile
import traceback

OURNAME = "devenv-awsenv"

CHANGES_DERIVED = set([
    "AWS_ACCESS_KEY_ID",
    "AWS_ACCOUNT_ID",
    "AWS_SECRET_ACCESS_KEY",
    "DEVENV_AWSENV_MFA_DEVICE_NAME",
    "DEVENV_AWSENV_MFA_OTP_AUTHSECRET",
])

REQUIRED = set([
    "AWS_ACCESS_KEY_ID",
    "AWS_ACCOUNT_ID",
    "AWS_DEFAULT_OUTPUT",
    "AWS_DEFAULT_REGION",
    "AWS_SECRET_ACCESS_KEY",
])

class Config:
    def __init__(self, env, keyring):
        if env is None:
            env = "dev"
        self.current_env = env
        self.keyring = keyring
        self.initialize_missing(self.current_env)
        self.envdata = self.load(self.current_env)
        derived = self.load_derived(self.current_env)
        if derived is None:
            self.save_derived(self.current_env, '{}')
            derived = self.load_derived(self.current_env)
        self.derived = derived

    def get_password(self, key, default=None):
        try:
            return self.keyring.get_password(OURNAME, key)
        except self.keyring.errors.InitError:
            return default

    def set_password(self, env, serialized):
        self.keyring.set_password(OURNAME, env, serialized)

    def get_changed(self, old, new):
        changed = set({ k: v for k, v in new.items() if old.get(k) != v })
        return changed

    def derived_after_changes(self, env, old, new):
        changed = self.get_changed(old, new)
        if CHANGES_DERIVED - changed:
            return '{}'
        return self.get_derived(env, '{}')

    def get_derived(self, env, default=None):
        derived = self.get_password(f"{env}-derived", default)
        return derived

    def get_missing(self, deserialized):
        missing = REQUIRED - set(deserialized)
        return missing

    def get_template(self):
        path = os.environ["DEVENV_AWSENV_TEMPLATE"]
        with open(path) as f:
            return f.read()

    def edit(self):
        env = self.current_env

        editor = os.environ.get('EDITOR', 'nano')

        old = self.get_password(env)

        old_deserialized = json.loads(old)

        with tempfile.NamedTemporaryFile(
                suffix=".json", mode="w+", delete=False) as tf:
            temp_filename = tf.name
            tf.write(old)
            tf.flush()

        try:
            cmd = shlex.split(editor)
            cmd.append(temp_filename)
            self.call(cmd)
            with open(temp_filename) as f:
                new = f.read()
                try:
                    new_deserialized = json.loads(new)
                except Exception:
                    self.save(env, new)
                    exc = traceback.format_exc()
                    self.errout(exc)
                    self.errout("Could not deserialize new data, re-edit")
                    return 1
                else:
                    missing = self.get_missing(new_deserialized)
                    if missing:
                        self.save(env, new)
                        self.errout(
                            f"missing required keys: {missing}, re-edit"
                        )
                        return 1
                    self.save(env, new)
                    derived = self.derived_after_changes(
                        env,
                        old_deserialized,
                        new_deserialized,
                    )
                    self.save_derived(env, derived)
                    if old_deserialized != new_deserialized:
                        self.show_activate_changes_tip()
        finally:
            os.unlink(temp_filename)

    def show_activate_changes_tip(self):
        self.errout(
            "To activate your changes, run:\n\n"
            '  awsenv auth && eval "$(awsenv export)"\n\n'
            "Or exit and reenter the devenv shell\n"
        )

    def save(self, env, serialized):
        self.set_password(env, serialized)

    def save_derived(self, env, serialized):
        self.set_password(f"{env}-derived", serialized)

    def load(self, env, default=None):
        serialized = self.get_password(env, default)
        try:
            return json.loads(serialized)
        except (json.decoder.JSONDecodeError, TypeError):
            return default

    def load_derived(self, env, default=None):
        return self.load(f"{env}-derived", default)

    def initialize_missing(self, env):
        meta_str = self.get_password("__meta__")
        if meta_str is None:
            meta_str = json.dumps({"envs": [self.current_env]})
        meta = json.loads(meta_str)
        if not env in meta["envs"]:
            meta["envs"].append(env)
        meta_str = json.dumps(meta, indent=4)
        self.set_password("__meta__", meta_str)
        env_str = self.get_password(env, None)
        if env_str is None:
            template = self.get_template()
            self.save(env, template)

    def get_meta(self):
        meta = self.get_password("__meta__")
        return meta

    def load_meta(self):
        meta = self.get_meta()
        return json.loads(meta)

    def serialize(self, config):
        serialized = json.dumps(config, indent=4, sort_keys=True)
        return serialized

    def mfaleft(self):
        exprstr = self.derived.get("AWS_SESSION_EXPIRES")
        if not exprstr:
            return "-"
        exprdt = datetime.fromisoformat(exprstr)
        nowutc = datetime.now(timezone.utc)
        exprdelta = exprdt - nowutc
        delta = str(exprdelta).split(".", 1)[0].rsplit(":", 1)[0]
        return delta

    def mfa_expired(self):
        delta = self.mfaleft()
        return delta.startswith("-")

    def mfacode(self):
        device = self.envdata.get("DEVENV_AWSENV_MFA_DEVICE")
        if not device:
            return None
        secret = self.envdata.get("DEVENV_AWSENV_MFA_OTP_AUTHSECRET")
        if secret:
            totp = pyotp.TOTP(secret)
            code = totp.now()
        else:
            code = input(f"Input AWS MFA code for {self.current_env}: ")
            code = code.strip()
            if not code:
                code = self.mfacode()
        return code

    def auth(self, force=False):
        expired = self.mfa_expired()

        if not (force or expired):
            return self.derived

        envdata = self.envdata
        device = envdata.get("DEVENV_AWSENV_MFA_DEVICE")
        if not device:
            return

        account_id = envdata["AWS_ACCOUNT_ID"]
        awsenv_aws = shutil.which("awsenv-aws")

        secret = envdata.get("DEVENV_AWSENV_MFA_OTP_AUTHSECRET")

        returncode = None

        while returncode != 0:
            code = self.mfacode()
            cmd = [
                awsenv_aws,
                "sts",
                "get-session-token",
                "--serial-number",
                f"arn:aws:iam::{account_id}:mfa/{device}",
                "--token-code",
                code
            ]
            result = self.run(cmd, env=envdata)
            self.errout(result.stderr)
            returncode = result.returncode
            if returncode != 0 and secret:
                sys.exit(1)

        response = json.loads(result.stdout)
        creds = response["Credentials"]
        derived = {
            "AWS_SESSION_TOKEN": creds["SessionToken"],
            "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
            "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
            "AWS_SESSION_EXPIRES": creds["Expiration"],
        }
        self.derived = derived
        self.save_derived(self.current_env, self.serialize(derived))
        self.errout(f"AWS MFA auth performed for {self.current_env}\n")
        return derived

    def list(self):
        meta = self.load_meta()
        envs = meta["envs"]
        current = self.current_env
        for env in sorted(envs):
            if env == current:
                self.out(f"{env} *")
            else:
                self.out(env)

    def delete(self, name):
        meta = self.load_meta()
        envs = meta["envs"]
        current = self.current_env
        if name == current:
            self.errout("Cannot delete current env")
            return 1
        if not name in envs:
            self.errout(f"No such env {name}")
            return 1
        envs.remove(name)
        meta = json.dumps(meta)
        self.set_password("__meta__", meta)
        self.keyring.delete_password(OURNAME, name)
        self.keyring.delete_password(OURNAME, f"{name}-derived")

    def copy(self, src, target):
        meta = self.load_meta()
        envs = meta["envs"]
        if not src in envs:
            self.errout(f"No such env {src}")
            return 1
        current = self.current_env
        if target == current:
            self.errout(f"Cannot copy on top of current env {target}")
            return 1
        copied = self.get_password(src)
        copied_derived = self.get_password(f"{src}-derived")
        if not target in envs:
            envs.append(target)
        self.save(target, copied)
        self.save_derived(target, copied_derived)
        self.set_password("__meta__", self.serialize({"envs":list(envs)} ))

    def create_aws_profile(self):
        p = f"awsenv-{self.current_env}"
        for varname, awsname in (
            ("AWS_ACCESS_KEY_ID", "aws_access_key_id"),
            ("AWS_SECRET_ACCESS_KEY", "aws_secret_access_key"),
            ("AWS_DEFAULT_OUTPUT", "output"),
            ("AWS_DEFAULT_REGION", "region"),
        ):
            val = self.envdata.get(varname)
            if val is not None:
                cmd = [
                    "awsenv-aws",
                    "configure",
                    "set",
                    awsname,
                    val,
                    "--profile",
                    p
                ]
                self.run(cmd)
        return p

    def export(self):
        envvars = {
            "DEVENV_AWSENV": self.current_env,
        }
        if os.environ.get("DEVENV_AWSENV_MANAGE_PROFILES"):
            envvars["AWS_PROFILE"] = self.create_aws_profile()
        envvars.update(self.envdata)
        envvars.update(self.derived)

        for k, v in sorted(envvars.items()):
            if not k.startswith("DEVENV_AWSENV_"):
                quoted = shlex.quote(v)
                self.out(f"{k}={quoted}")
                self.out(f"export {k}")

    def run(self, cmd, **kw): # pragma: no cover
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            **kw
        )

    def call(self, cmd): # pragma: no cover
        return subprocess.call(cmd)

    def out(self, data): # pragma: no cover
        print(data)

    def errout(self, data): # pragma: no cover
        sys.stderr.write(data + "\n")
        sys.stderr.flush()

if __name__ == "__main__": # pragma: no cover
    main_parser = argparse.ArgumentParser(description="awsenv")
    subparsers= main_parser.add_subparsers(
        dest="command",
        required=False,
        help="No arguments means show current default awsenv"
    )
    edit_parser = subparsers.add_parser(
        "edit", help="Edit the current environment"
    )

    auth_parser = subparsers.add_parser(
        "auth", help="Supply authentication values (e.g. for MFA) if neccesary"
    )
    auth_parser.add_argument(
        "--force",
        help="Force MFA even if credentials are not expired",
        action="store_true",
        default=False,
    )

    list_parser = subparsers.add_parser(
        "list", help="Show all available environments"
    )

    delete_parser = subparsers.add_parser(
        "delete", help="Delete an environment"
    )
    delete_parser.add_argument(
        "name", help="The environment name to delete"
    )

    copy_parser = subparsers.add_parser(
        "copy", help="Copy an environment"
    )
    copy_parser.add_argument(
        "source", help="The source environment name"
    )
    copy_parser.add_argument(
        "target", help="The target environment name"
    )

    export_parser = subparsers.add_parser(
        "export", help="Output shell commands to export the required envvars"
    )
    mfaleft_parser = subparsers.add_parser(
        "mfaleft",
        help="Show how much time is left in the current MFA session (hh:mm)"
    )

    args = main_parser.parse_args()

    try:
        import keyring
    except ImportError:
        keyring = None # for tests

    env = os.environ.get("DEVENV_AWSENV")
    config = Config(env, keyring)

    def exit(returncode):
        if returncode is None:
            returncode = 0
        sys.exit(returncode)

    if not args.command:
        print(config.current_env)

    if args.command == "edit":
        exit(config.edit())

    if args.command == "auth":
        exit(config.auth(args.force))

    if args.command == "mfaleft":
        exit(print(config.mfaleft()))

    if args.command == "list":
        exit(config.list())

    if args.command == "delete":
        exit(config.delete(args.name))

    if args.command == "copy":
        exit(config.copy(args.source, args.target))

    if args.command == "export":
        exit(config.export())
