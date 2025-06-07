import argparse
from datetime import datetime, timezone
import json
import keyring
import os
import pyotp
import shlex
import shutil
import subprocess
import sys
import tempfile

OURNAME = "devenv-awsenv"

KEYS = set([
    "AWS_ACCESS_KEY_ID",
    "AWS_ACCOUNT_ID",
    "AWS_DEFAULT_OUTPUT",
    "AWS_DEFAULT_REGION",
    "AWS_SECRET_ACCESS_KEY",
    "DEVENV_AWSENV_MFA_DEVICE_NAME",
    "DEVENV_AWSENV_MFA_OTP_AUTHSECRET",
])

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
    def __init__(self, current_env):
        self.current_env = self.get_default_env()
        envdata = self.load(self.current_env)
        if envdata is None:
            template = self.get_template()
            self.save(template)
        derived = self.load_derived(self.current_env)
        if derived is None:
            self.save_derived('{}')
            derived = {}
        self.envdata = envdata
        self.derived = derived

    def get_password(self, key, default=None):
        try:
            return keyring.get_password(OURNAME, key)
        except keyring.errors.InitError:
            return default

    def set_password(self, env, serialized):
        keyring.set_password(OURNAME, env, serialized)

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
        dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(dir, "template.json")) as f:
            return f.read()

    def edit(self, env):
        if env is None:
            env = self.current_env

        editor = os.environ.get('EDITOR', 'nano')

        old = self.get_password(env)

        template = self.get_template()

        if old is None:
            old = template

        try:
            old_deserialized = json.loads(old)
        except Exception:
            old_deserialized = {}

        with tempfile.NamedTemporaryFile(
                suffix=".json", mode="w+", delete=False) as tf:
            temp_filename = tf.name
            tf.write(old)
            tf.flush()

        try:
            cmd = shlex.split(editor)
            cmd.append(temp_filename)
            subprocess.call(cmd)
            with open(temp_filename) as f:
                new = f.read()
                try:
                    new_deserialized = json.loads(new)
                except Exception:
                    self.save(env, new)
                    import traceback; traceback.print_exc()
                    print("Could not deserialize new data, reedit")
                    return
                else:
                    missing = self.get_missing(new_deserialized)
                    if missing:
                        self.save(env, new)
                        raise ValueError(
                            f"missing required keys: {missing}, re-edit"
                        )
                    self.save(env, new)
                    derived = self.derived_after_changes(
                        env,
                        old_deserialized,
                        new_deserialized,
                    )
                    self.save_derived(env, derived)
        finally:
            os.unlink(temp_filename)

    def save(self, env, serialized):
        self.set_password(env, serialized)

    def save_derived(self, env, serialized):
        self.set_password(f"{env}-derived", serialized)

    def load(self, env, default=None):
        serialized = self.get_password(env, default)
        try:
            return json.loads(serialized)
        except json.decoder.JSONDecodeError:
            return default

    def load_derived(self, env, default=None):
        return self.load(f"{env}-derived", default)

    def get_meta(self):
        meta = self.get_password("__meta__")
        if meta is None:
            meta = json.dumps({"envs": ["dev"]}, indent=4)
            self.set_password("__meta__", meta)
        return meta

    def load_meta(self):
        meta = self.get_meta()
        return json.loads(meta)

    def serialize(self, config):
        serialized = json.dumps(config, indent=4, sort_keys=True)
        return serialized

    def get_default_env(self):
        meta = json.loads(self.get_meta())
        return meta["envs"][0]

    def switch(self, env):
        meta = json.loads(self.get_meta())
        if not env in meta["envs"]:
            raise ValueError(f"no such env named {env}")
        meta["envs"].remove(env)
        meta["envs"].insert(0, env)
        meta = json.dumps(meta, indent=2)
        self.set_password("__meta__", meta)

    def get_aws_session_expires(self):
        return self.derived.get("AWS_SESSION_EXPIRES")

    def get_mfa_delta(self):
        exprstr = self.get_aws_session_expires()
        if not exprstr:
            return "-"
        exprdt = datetime.fromisoformat(exprstr)
        nowutc = datetime.now(timezone.utc)
        exprdelta = exprdt - nowutc
        delta = str(exprdelta).split(".", 1)[0].rsplit(":", 1)[0]
        return delta

    def mfa_expired(self):
        delta = self.get_mfa_delta()
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
            code = input("Input current MFA code: ")
        return code.strip()

    def mfa(self, code, force=False):
        expired = self.mfa_expired()

        if not (force or expired):
            return self.derived

        envdata = self.envdata
        device = envdata.get("DEVENV_AWSENV_MFA_DEVICE")
        if not device:
            raise ValueError("No DEVENV_AWSENV_MFA_DEVICE defined in config")
        account_id = envdata["AWS_ACCOUNT_ID"]
        awsenv_aws = shutil.which("awsenv-aws")
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
        if result.returncode == 0:
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
            sys.stderr.write("mfa auth performed")
            sys.stderr.flush()
            return derived
        else:
            print("mfa auth failed")
            sys.stderr.write(result.stderr)
            sys.stderr.flush()

    def list(self):
        meta = self.load_meta()
        envs = meta["envs"]
        current = envs[0]
        for env in sorted(envs):
            sys.stdout.write(env)
            if env == current:
                print("*")
            else:
                print()

    def delete(self, name):
        meta = self.load_meta()
        envs = meta["envs"]
        current = envs[0]
        if name == current:
            print("Cannot delete current env")
            sys.exit(1)
        if not name in envs:
            print(f"No such env {name}")
            sys.exit(1)
        envs.remove(name)
        meta = json.dumps(meta)
        self.set_password("__meta__", meta)
        keyring.delete_password(OURNAME, name)
        keyring.delete_password(OURNAME, "{name}-derived")

    def copy(self, src, target):
        meta = self.load_meta()
        envs = meta["envs"]
        if not src in envs:
            print(f"No such env {src}")
            sys.exit(1)
        current = envs[0]
        if target == current:
            print(f"Cannot copy on top of current env {target}")
            sys.exit(1)
        copied = self.get_password(src)
        copied_derived = self.get_password(f"{src}-derived")
        if not target in envs:
            envs.append(target)
        self.save(target, copied)
        self.save_derived(target, copied_derived)
        self.set_password("__meta__", self.serialize({"envs":list(envs)} ))

    def create_aws_profile(self):
        p = self.envdata.get("AWS_PROFILE")
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

    def export(self):
        envvars = {}
        envvars.update(self.envdata)
        if "DEVENV_AWS_ENV_MFA_DEVICE" in envvars:
            derived = None
            while derived is None:
                code = self.mfacode()
                derived = self.mfa(code)
        else:
            derived = self.derived
        envvars.update(derived)

        for k, v in sorted(envvars.items()):
            if not k =="DEVENV_AWSENV_MFA_OTP_AUTHSECRET":
                quoted = shlex.quote(v)
                print(f"{k}={quoted}")
                print(f"export {k}")

    def run(self, cmd, **kw):
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            **kw
        )

if __name__ == "__main__":
    main_parser = argparse.ArgumentParser(description="awsenv")
    subparsers= main_parser.add_subparsers(
        dest="command",
        required=False,
        help="No arguments means show current default awsenv"
    )
    edit_parser = subparsers.add_parser(
        "edit", help="Edit an environment"
    )
    edit_parser.add_argument(
        "name", help="The environment name to edit", default=None, nargs="?"
    )

    mfa_parser = subparsers.add_parser(
        "mfa", help="Add mfa result to derived"
    )

    switch_parser = subparsers.add_parser(
        "switch", help="Make an environment the default"
    )
    switch_parser.add_argument(
        "name", help="The environment name to switch to"
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
        "copy", help="Delete an environment"
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

    args = main_parser.parse_args()

    env = os.environ.get("DEVENV_AWSENV", "dev")
    config = Config(env)

    if not args.command:
        print(config.current_env)

    if args.command == "edit":
        config.edit(args.name)

    if args.command == "mfa":
        config.mfa()

    if args.command == "switch":
        config.switch(args.name)

    if args.command == "list":
        config.list()

    if args.command == "delete":
        config.delete(args.name)

    if args.command == "copy":
        config.copy(args.source, args.target)

    if args.command == "export":
        config.export()
