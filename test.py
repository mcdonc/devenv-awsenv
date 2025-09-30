import json
import os
import unittest

class FakeErrors:
    InitError = Exception

class FakeKeyring:
    errors = FakeErrors()
    def __init__(self):
        self.meta = None
        self.envs = {}

    def get_password(self, ourname, key):
        import keyring
        if key == "__meta__":
            if self.meta is None:
                raise keyring.errors.InitError
            return self.meta
        env = self.envs.get(key)
        if env is None:
            raise keyring.errors.InitError
        return env

    def set_password(self, ourname, key, serialized):
        if key == '__meta__':
            self.meta = serialized
        else:
            self.envs[key] = serialized

    def delete_password(self, ourname, key):
        self.envs.pop(key, None)

class TestConfig(unittest.TestCase):
    def __init__(self, name):
        super().__init__(name)
        here = os.path.dirname(os.path.abspath(__file__))
        self.template_path = os.path.join(here, "template.json")
        os.environ["DEVENV_AWSENV_TEMPLATE"] = self.template_path

    def _makeOne(self, env, keyring=None):
        from awsenv import Config
        if keyring is None:
            keyring = FakeKeyring()
        config = Config(env, keyring)
        return config

    def test_ctor_noenv(self):
        keyring = FakeKeyring()
        config = self._makeOne(None, keyring)
        self.assertEqual(config.current_env, "dev")
        self.assertEqual(
            json.loads(config.keyring.meta),
            json.loads('{"envs": ["dev"]}')
        )
        with open(self.template_path) as f:
            self.assertEqual(
                config.keyring.envs["dev"],
                f.read()
            )
        self.assertEqual(
            config.keyring.envs["dev-derived"],
            '{}'
        )

    def test_ctor_withenv(self):
        keyring = FakeKeyring()
        config = self._makeOne("dev", keyring)
        self.assertEqual(config.current_env, "dev")
        self.assertEqual(
            json.loads(config.keyring.meta),
            json.loads('{"envs": ["dev"]}')
        )
        with open(self.template_path) as f:
            self.assertEqual(
                config.keyring.envs["dev"],
                f.read()
            )
        self.assertEqual(
            config.keyring.envs["dev-derived"],
            '{}'
        )

    def test_edit_changes_noerror(self):
        config = self._makeOne("profile")
        new = """
        {"AWS_ACCOUNT_ID":"a",
        "AWS_SECRET_ACCESS_KEY":"b",
        "AWS_DEFAULT_REGION":"c",
        "AWS_ACCESS_KEY_ID":"d",
        "AWS_DEFAULT_OUTPUT":"e"}
        """
        def call(cmd):
            fn = cmd[-1]
            with open(fn, "w") as f:
                f.write(new)
        config.call = call
        capture = []
        config.errout = capture.append
        config.edit()
        self.assertEqual(config.keyring.envs["profile"], new)
        self.assertEqual(config.keyring.envs["profile-derived"], '{}')
        self.assertTrue(capture[0].startswith("To activate"))

    def test_edit_changes_witherror(self):
        config = self._makeOne("profile")
        new = """
        {"AWS_ACCOUNT_ID":"a",
        "AWS_SECRET_ACCESS_KEY":"b",
        "AWS_DEFAULT_REGION":"c",
        "AWS_ACCESS_KEY_ID":"d",
        "AWS_DEFAULT_OUTPUT":"e
        """
        def call(cmd):
            fn = cmd[-1]
            with open(fn, "w") as f:
                f.write(new)
        config.call = call
        capture = []
        config.errout = capture.append
        config.edit()
        self.assertEqual(config.keyring.envs["profile"], new)
        self.assertTrue(capture[1].startswith("Could not deserialize"))

    def test_edit_changes_withmissing(self):
        config = self._makeOne("profile")
        new = """
        {"AWS_ACCOUNT_ID":"a",
        "AWS_SECRET_ACCESS_KEY":"b",
        "AWS_DEFAULT_REGION":"c",
        "AWS_DEFAULT_OUTPUT":"e"}
        """
        def call(cmd):
            fn = cmd[-1]
            with open(fn, "w") as f:
                f.write(new)
        config.call = call
        capture = []
        config.errout = capture.append
        config.edit()
        self.assertEqual(config.keyring.envs["profile"], new)
        self.assertEqual(
            capture[0],
            "missing required keys: {'AWS_ACCESS_KEY_ID'}, re-edit"
        )

    def test_edit_nochanges(self):
        config = self._makeOne("profile")
        new = config.keyring.envs["profile"]
        def call(cmd):
            fn = cmd[-1]
            with open(fn, "w") as f:
                f.write(new)
        config.call = call
        capture = []
        config.errout = capture.append
        config.edit()
        self.assertEqual(config.keyring.envs["profile"], new)
        self.assertFalse(capture)

    def test_load_cant_deserialize(self):
        config = self._makeOne("profile")
        config.keyring.envs["profile"] = "{malformed"
        result = config.load("profile", 123)
        self.assertEqual(result, 123)

    def test_copy_no_such_profile(self):
        config = self._makeOne("profile")
        capture = []
        config.errout = capture.append
        config.copy("wontexist", "another")
        self.assertEqual(capture[0], "No such env wontexist")

    def test_copy_atop_current(self):
        config = self._makeOne("profile")
        capture = []
        config.errout = capture.append
        config.copy("profile", "profile")
        self.assertEqual(
            capture[0],
            "Cannot copy on top of current env profile"
        )

    def test_copy_success(self):
        config = self._makeOne("profile")
        config.copy("profile", "another")
        self.assertEqual(
            config.keyring.envs["profile"],
            config.keyring.envs["another"]
        )

    def test_delete_current(self):
        config = self._makeOne("profile")
        capture = []
        config.errout = capture.append
        config.delete("profile")
        self.assertEqual(capture[0], "Cannot delete current env")

    def test_delete_nosuch(self):
        config = self._makeOne("profile")
        capture = []
        config.errout = capture.append
        config.delete("nope")
        self.assertEqual(capture[0], "No such env nope")

    def test_delete_works(self):
        config = self._makeOne("profile")
        config.keyring.envs["another"] = "{}"
        config.keyring.envs["another-derived"] = "{}"
        meta = json.loads(config.keyring.meta)
        meta["envs"] = ["profile", "another"]
        config.keyring.meta = json.dumps(meta)
        capture = []
        config.errout = capture.append
        config.delete("another")
        self.assertFalse(capture)
        self.assertEqual(
            list(config.keyring.envs.keys()), ["profile", "profile-derived"]
        )
        self.assertEqual(
            json.loads(config.keyring.meta),
            {"envs": ["profile"]}
        )

    def test_list(self):
        config = self._makeOne("profile")
        config.keyring.envs["another"] = "{}"
        meta = json.loads(config.keyring.meta)
        meta["envs"] = ["profile", "another"]
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
            "AWS_ACCESS_KEY_ID=''",
            "export AWS_ACCESS_KEY_ID",
            "AWS_ACCOUNT_ID=''",
            "export AWS_ACCOUNT_ID",
            "AWS_DEFAULT_OUTPUT=json",
            "export AWS_DEFAULT_OUTPUT",
            "AWS_DEFAULT_REGION=us-east-1",
            "export AWS_DEFAULT_REGION",
            "AWS_SECRET_ACCESS_KEY=''",
            "export AWS_SECRET_ACCESS_KEY",
            "DEVENV_AWSENV=profile",
            "export DEVENV_AWSENV",
        ])
        self.assertEqual(actual, expected)

    def test_initialize_missing(self):
        config = self._makeOne("profile")
        config.initialize_missing("another")
        self.assertEqual(config.get_password("another"), config.get_template())

    def test_get_changed_withchanged(self):
        config = self._makeOne("profile")
        old = {"a":1, "b":2}
        new = {"a":1, "b":3}
        result = config.get_changed(old, new)
        self.assertEqual(result, {'b'})

    def test_get_changed_nochanged(self):
        config = self._makeOne("profile")
        old = {"a":1, "b":2}
        new = {"a":1, "b":2}
        result = config.get_changed(old, new)
        self.assertEqual(result, set())

    def test_derived_after_changes_nochanges(self):
        config = self._makeOne("profile")
        old = {
            "AWS_ACCESS_KEY_ID":"1",
            "AWS_ACCOUNT_ID":"1",
            "AWS_SECRET_ACCESS_KEY":"1",
            "DEVENV_AWSENV_MFA_DEVICE":"1",
            "DEVENV_AWSENV_MFA_OTP_AUTHSECRET":"1",
            }
        new = {
            "AWS_ACCESS_KEY_ID":"1",
            "AWS_ACCOUNT_ID":"1",
            "AWS_SECRET_ACCESS_KEY":"1",
            "DEVENV_AWSENV_MFA_DEVICE":"1",
            "DEVENV_AWSENV_MFA_OTP_AUTHSECRET":"1",
            }
        result = config.derived_after_changes("profile", old, new)
        self.assertEqual(result, '{}')

    def test_derived_after_changes_withchanges(self):
        config = self._makeOne("profile")
        config.keyring.envs["profile-derived"] = '{"a":"5"}'
        old = {
            "AWS_ACCESS_KEY_ID":"1",
            "AWS_ACCOUNT_ID":"1",
            "AWS_SECRET_ACCESS_KEY":"1",
            "DEVENV_AWSENV_MFA_DEVICE":"1",
            "DEVENV_AWSENV_MFA_OTP_AUTHSECRET":"1",
            }
        new = {
            "AWS_ACCESS_KEY_ID":"2",
            "AWS_ACCOUNT_ID":"2",
            "AWS_SECRET_ACCESS_KEY":"2",
            "DEVENV_AWSENV_MFA_DEVICE":"2",
            "DEVENV_AWSENV_MFA_OTP_AUTHSECRET":"2",
            }
        result = config.derived_after_changes("profile", old, new)
        self.assertEqual(result, '{"a":"5"}')

    def test_mfaleft_no_aws_session_expires(self):
        config = self._makeOne("profile")
        self.assertEqual(config.mfaleft(), '-')

    def test_mfaleft_with_aws_session_expires(self):
        config = self._makeOne("profile")
        config.derived["AWS_SESSION_EXPIRES"] = '2037-01-01T08:57:37+00:00'
        self.assertTrue("days" in config.mfaleft())

    def test_mfa_expired_no_aws_session_expires(self):
        config = self._makeOne("profile")
        self.assertEqual(config.mfa_expired(), True)

    def test_mfa_expired_with_aws_session_expires(self):
        config = self._makeOne("profile")
        config.derived["AWS_SESSION_EXPIRES"] = '2037-01-01T08:57:37+00:00'
        self.assertEqual(config.mfa_expired(), False)

    def test_mfacode_nodevice(self):
        config = self._makeOne("profile")
        self.assertEqual(config.mfacode(), None)

    def test_mfacode_withdevice_nosecret(self):
        config = self._makeOne("profile")
        config.envdata["DEVENV_AWSENV_MFA_DEVICE"] = "device"
        config.inp = lambda x: "12345"
        self.assertEqual(config.mfacode(), "12345")

    def test_mfacode_withdevice_withsecret(self):
        config = self._makeOne("profile")
        config.envdata["DEVENV_AWSENV_MFA_DEVICE"] = "device"
        config.envdata["DEVENV_AWSENV_MFA_OTP_AUTHSECRET"] = "E2OVN6XH7LXUR22ZQ64MAEM2NQ22JEKILF3QUV7W7S6JHYL5BZVAFZNDDLSRW3AZ"
        self.assertEqual(len(config.mfacode()), 6)

    def test_create_aws_profile(self):
        config = self._makeOne("profile")
        L = []
        config.run = lambda cmd: L.append(cmd)
        result = config.create_aws_profile()
        self.assertEqual(result, "awsenv-profile")
        expected = [['awsenv-aws',
                     'configure',
                     'set',
                     'aws_access_key_id',
                     '',
                     '--profile',
                     'awsenv-profile'],
                    ['awsenv-aws',
                     'configure',
                     'set',
                     'aws_secret_access_key',
                     '',
                     '--profile',
                     'awsenv-profile'],
                    ['awsenv-aws',
                     'configure',
                     'set',
                     'output',
                     'json',
                     '--profile',
                     'awsenv-profile'],
                    ['awsenv-aws',
                     'configure',
                     'set',
                     'region',
                     'us-east-1',
                     '--profile',
                     'awsenv-profile']]
        self.assertEqual(L, expected)

    def test_auth_nodevice(self):
        config = self._makeOne("profile")
        self.assertEqual(config.auth(), 0)

    def test_auth_notexpired(self):
        config = self._makeOne("profile")
        config.envdata["DEVENV_AWSENV_MFA_DEVICE"] = "device"
        config.derived["AWS_SESSION_EXPIRES"] = '2037-01-01T08:57:37+00:00'
        self.assertEqual(config.auth(), 0)

    def test_auth_expired_no_authsecret_success(self):
        config = self._makeOne("profile")
        config.envdata["DEVENV_AWSENV_MFA_DEVICE"] = "device"
        config.envdata["AWS_ACCOUNT_ID"] = '123'
        config.derived["AWS_SESSION_EXPIRES"] = '2022-01-01T08:57:37+00:00'
        config.which = lambda cmd: cmd
        config.inp = lambda x: "12345"
        config.errout = lambda cmd: 0
        class Result:
            pass
        def run(cmd, env):
            self.assertEqual(cmd[0], "awsenv-aws")
            result = Result()
            result.returncode = 0
            result.stderr = ''
            result.stdout = json.dumps(
                {"Credentials":
                 {
                     "SessionToken": "token",
                     "SecretAccessKey": "key",
                     "AccessKeyId": "id",
                     "Expiration": "expires",
                 }
                 }
            )
            return result
        config.run = run
        self.assertEqual(config.auth(), 0)
        self.assertEqual(
            config.derived,
            {
                "AWS_SESSION_TOKEN":"token",
                "AWS_ACCESS_KEY_ID":"id",
                "AWS_SECRET_ACCESS_KEY":"key",
                "AWS_SESSION_EXPIRES":"expires"
             }
        )

    def test_auth_expired_with_authsecret_success(self):
        config = self._makeOne("profile")
        config.envdata["DEVENV_AWSENV_MFA_DEVICE"] = "device"
        config.envdata["DEVENV_AWSENV_MFA_OTP_AUTHSECRET"] = "E2OVN6XH7LXUR22ZQ64MAEM2NQ22JEKILF3QUV7W7S6JHYL5BZVAFZNDDLSRW3AZ"
        config.envdata["AWS_ACCOUNT_ID"] = '123'
        config.derived["AWS_SESSION_EXPIRES"] = '2022-01-01T08:57:37+00:00'
        config.which = lambda cmd: cmd
        config.inp = lambda x: "12345"
        config.errout = lambda cmd: 0
        class Result:
            pass
        def run(cmd, env):
            self.assertEqual(cmd[0], "awsenv-aws")
            result = Result()
            result.returncode = 0
            result.stderr = ''
            result.stdout = json.dumps(
                {"Credentials":
                 {
                     "SessionToken": "token",
                     "SecretAccessKey": "key",
                     "AccessKeyId": "id",
                     "Expiration": "expires",
                 }
                 }
            )
            return result
        config.run = run
        self.assertEqual(config.auth(), 0)
        self.assertEqual(
            config.derived,
            {
                "AWS_SESSION_TOKEN":"token",
                "AWS_ACCESS_KEY_ID":"id",
                "AWS_SECRET_ACCESS_KEY":"key",
                "AWS_SESSION_EXPIRES":"expires"
             }
        )

if __name__ == '__main__':
    unittest.main()
