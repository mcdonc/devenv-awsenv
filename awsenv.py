import argparse
import json
import keyring
import os
import subprocess
import tempfile

ourname = "devenv-awsenv"

class Config:
    def __init__(self, current_env):
        self.current_env = current_env

    def get_template(self):
        dir = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(dir, "template.json")) as f:
            return f.read()

    def edit(self, env):
        editor = os.environ.get('EDITOR', 'nano')

        try:
            serialized = keyring.get_password(ourname, env)
        except keyring.errors.InitError:
            serialized = None
            
        if serialized is None:
            serialized = self.get_template()

        with tempfile.NamedTemporaryFile(
                suffix=".tmp", mode="w+", delete=False) as tf:
            temp_filename = tf.name
            tf.write(serialized)
            tf.flush()

        try:
            subprocess.call([editor, temp_filename])
            with open(temp_filename) as f:
                new = f.read()
                try:
                    json.loads(new)
                except Exception:
                    print(new)
                    print("Copy this value back into the editor and try again")
                    import traceback; traceback.print_exc()
                else:
                    if new != serialized:
                        self._import(env, temp_filename)
        finally:
            os.unlink(temp_filename)
        
    def _import(self, env, path):
        with open(path) as f:
            serialized = f.read()
            self._save(env, serialized)
        
    def _save(self, env, serialized):
        keyring.set_password(ourname, env, serialized)

    def save(self, env, config):
        serialized = self.serialize(config)
        return self._save(env, serialized)

    def serialize(self, config):
        serialized = json.dumps(config, indent=2)
        return serialized
        
    def deserialize(self, env):
        serialized = keyring.get_password(ourname, env)
        if serialized is None:
            serialized = "{}"
        deserialized = json.loads(serialized)
        return deserialized

    def get_meta(self):
        meta = keyring.get_password(ourname, "__meta__")
        if meta is None:
            meta = json.dumps({"envs": ["dev"]}, indent=2)
            keyring.set_password(ourname, "__meta__", meta)
        return meta

    def default(self, env):
        meta = json.loads(self.get_meta())
        if not env in meta["envs"]:
            meta["envs"].insert(0, env)
        meta["envs"].remove(env)
        meta["envs"].insert(0, env)
        meta = json.dumps(meta, indent=2)
        keyring.set_password(ourname, "__meta__", meta)

if __name__ == "__main__":
    main_parser = argparse.ArgumentParser(description="awsenv")
    subparsers= main_parser.add_subparsers(
        dest="command",
        required = True,
    )
    edit_parser = subparsers.add_parser("edit", help="Edit an environment")
    edit_parser.add_argument("name", help="The environment name to edit")
    args = main_parser.parse_args()

    env = os.environ.get("DEVENV_AWSENV")
    config = Config(env)

    if args.command == "edit":
        config.edit(args.name)
        
    func = getattr(config, args.command)
        
