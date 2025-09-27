{ ... }:

{
  imports = [ ./default.nix ];

  awsenv.enable = true;
  awsenv.profile = "testenv";

  enterShell = ''
    [ "$(awsenv)" == "testenv" ] && echo "enterShell works" || exit 2
    awsenv export | grep DEVENV_AWSENV || exit 2
    env | grep DEVENV_AWSENV || exit 2
  '';

  enterTest = ''
    awsenvpyexe -m coverage run "$DEVENV_ROOT/test.py"
    awsenvpyexe -m coverage report -m \
      --fail-under=100 \
      --include="test.py,awsenv.py"
  '';
}
