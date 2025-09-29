import json
import os
import unittest

class FakeErrors:
    InitError = Exception

class FakeKeyring:
    errors = FakeErrors()
    def __init__(self):
        self.meta = None
        self.profiles = {}

    def get_password(self, ourname, key):
        import keyring
        if key == "__meta__":
            if self.meta is None:
                raise keyring.errors.InitError
            return self.meta
        profile = self.profiles.get(key)
        if profile is None:
            raise keyring.errors.InitError
        return profile

    def set_password(self, ourname, key, serialized):
        if key == '__meta__':
            self.meta = serialized
        else:
            self.profiles[key] = serialized

    def delete_password(self, ourname, key):
        self.profiles.pop(key, None)

class TestConfig(unittest.TestCase):
    def __init__(self, name):
        super().__init__(name)
        here = os.path.dirname(os.path.abspath(__file__))
        self.template_path = os.path.join(here, "template.json")
        os.environ["DEVENV_SECRETS_TEMPLATE"] = self.template_path

    def _makeOne(self, env, keyring=None):
        from awsenv import Config
        if keyring is None:
            keyring = FakeKeyring()
        config = Config(env, keyring)
        return config

    def test_ctor_noprofile(self):
        keyring = FakeKeyring()
        config = self._makeOne(None, keyring)
        self.assertEqual(config.current_env, "dev")
        self.assertEqual(
            json.loads(config.keyring.meta),
            json.loads('{"profiles": ["dev"]}')
        )
        with open(self.template_path) as f:
            self.assertEqual(
                config.keyring.profiles["dev"],
                f.read()
            )

    def test_ctor_withprofile(self):
        keyring = FakeKeyring()
        config = self._makeOne("profile", keyring)
        self.assertEqual(config.current_env, "profile")
        self.assertEqual(
            json.loads(config.keyring.meta),
            json.loads('{"profiles": ["profile"]}')
        )
        with open(self.template_path) as f:
            self.assertEqual(
                config.keyring.profiles["profile"],
                f.read()
            )

    def test_edit_changes_noerror(self):
        config = self._makeOne("profile")
        new = '{"SECRET1":"a"}'
        def call(cmd):
            fn = cmd[-1]
            with open(fn, "w") as f:
                f.write(new)
        config.call = call
        capture = []
        config.errout = capture.append
        config.edit()
        self.assertEqual(config.keyring.profiles["profile"], new)
        self.assertTrue(capture[0].startswith("To activate"))

    def test_edit_changes_witherror(self):
        config = self._makeOne("profile")
        new = '{"SECRET1":"a}'
        def call(cmd):
            fn = cmd[-1]
            with open(fn, "w") as f:
                f.write(new)
        config.call = call
        capture = []
        config.errout = capture.append
        config.edit()
        self.assertEqual(config.keyring.profiles["profile"], new)
        self.assertTrue(capture[1].startswith("Could not deserialize"))

    def test_edit_nochanges(self):
        config = self._makeOne("profile")
        new = config.keyring.profiles["profile"]
        def call(cmd):
            fn = cmd[-1]
            with open(fn, "w") as f:
                f.write(new)
        config.call = call
        capture = []
        config.errout = capture.append
        config.edit()
        self.assertEqual(config.keyring.profiles["profile"], new)
        self.assertFalse(capture)

    def test_load_cant_deserialize(self):
        config = self._makeOne("profile")
        config.keyring.profiles["profile"] = "{malformed"
        result = config.load("profile", 123)
        self.assertEqual(result, 123)

    def test_copy_no_such_profile(self):
        config = self._makeOne("profile")
        capture = []
        config.errout = capture.append
        config.copy("wontexist", "another")
        self.assertEqual(capture[0], "No such profile wontexist")

    def test_copy_atop_current(self):
        config = self._makeOne("profile")
        capture = []
        config.errout = capture.append
        config.copy("profile", "profile")
        self.assertEqual(
            capture[0],
            "Cannot copy on top of current profile profile"
        )

    def test_copy_success(self):
        config = self._makeOne("profile")
        config.copy("profile", "another")
        self.assertEqual(
            config.keyring.profiles["profile"],
            config.keyring.profiles["another"]
        )

    def test_delete_current(self):
        config = self._makeOne("profile")
        capture = []
        config.errout = capture.append
        config.delete("profile")
        self.assertEqual(capture[0], "Cannot delete current profile")

    def test_delete_nousuch(self):
        config = self._makeOne("profile")
        capture = []
        config.errout = capture.append
        config.delete("nope")
        self.assertEqual(capture[0], "No such profile nope")

    def test_delete_works(self):
        config = self._makeOne("profile")
        config.keyring.profiles["another"] = "{}"
        meta = json.loads(config.keyring.meta)
        meta["profiles"] = ["profile", "another"]
        config.keyring.meta = json.dumps(meta)
        capture = []
        config.errout = capture.append
        config.delete("another")
        self.assertFalse(capture)
        self.assertEqual(list(config.keyring.profiles.keys()), ["profile"])
        self.assertEqual(
            json.loads(config.keyring.meta),
            {"profiles": ["profile"]}
        )

    def test_list(self):
        config = self._makeOne("profile")
        config.keyring.profiles["another"] = "{}"
        meta = json.loads(config.keyring.meta)
        meta["profiles"] = ["profile", "another"]
        config.keyring.meta = json.dumps(meta)
        capture = []
        config.out = capture.append
        config.list()
        self.assertEqual(capture, ['another', 'profile *'])

    def test_export(self):
        config = self._makeOne("profile")
        capture = []
        config.out = capture.append
        config.export()
        actual = '\n'.join(capture)
        expected = '\n'.join([
            "DEVENV_SECRETS_PROFILE=profile",
            "export DEVENV_SECRETS_PROFILE",
            "MYSECRET=secret",
            "export MYSECRET",
            "MYSECRET2=secret2",
            "export MYSECRET2"
        ])
        self.assertEqual(actual, expected)

    def test_initialize_missing(self):
        config = self._makeOne("profile")
        config.initialize_missing("another")
        self.assertEqual(config.get_password("another"), config.get_template())


if __name__ == '__main__':
    unittest.main()
