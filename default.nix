{ pkgs, lib, config, ... }:

{
  options.awsenv = {
    enable = lib.mkOption {
      type = lib.types.bool;
      description = "Use Devenv AWS environments";
      default = false;
    };
    profile = lib.mkOption {
      type = lib.types.str;
      description = "Use this AWS profile at devenv startup";
      default = "dev";
    };
    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.awscli2;
      defaultText = lib.literalExpression "pkgs.awscli2";
      description = "The awscli2 pacakge that awsenv should use to do auth";
    };
    manage-profiles = lib.mkOption {
      type = lib.types.bool;
      description = "Manage the AWS_PROFILE envvar and add profiles to ~/.aws";
      default = false;
    };
  };
  config =
    let
      cfg = config.awsenv;
      # Separate python used by the devenv for keyring-related tasks.
      # Rationale: on Mac, when any of this stuff changes, its Nix store path
      # will change, and the Mac will ask for confirmation to allow the "new"
      # Python access for each password in the keyring.
      #
      # Linux systems need either dbus-python (KDE) or secretstorage (GNOME).
      # but Macs don't.
      #
      # Use python311 to get secretstorage/cryptography to work (fails under
      # 3.12 with "cannot import name 'exceptions' from
      # 'cryptography.hazmat.bindings._rust' (unknown location)" because for
      # whatever reason, the cryptography package has a python-3.11 DLL instead
      # of a python-3.12 one in Nix.
      #
      awsenv_python = (
        pkgs.python311.withPackages (python-pkgs: [
          python-pkgs.keyring
          python-pkgs.keyrings-alt
          python-pkgs.pyotp
          python-pkgs.coverage
        ] ++ lib.optionals pkgs.stdenv.isLinux [
          python-pkgs.dbus-python
          python-pkgs.secretstorage
        ]
        )
      );
      awsenvpyexe = "${awsenv_python}/bin/python";
    in
      lib.mkIf cfg.enable {
        scripts.awsenv.exec = lib.mkDefault ''exec ${awsenvpyexe} "${./awsenv.py}" $@'';
        scripts.awsenvpyexe.exec = lib.mkDefault ''exec ${awsenvpyexe} $@'';
        scripts.awsenv-aws.exec = lib.mkDefault ''exec ${cfg.package}/bin/aws $@'';
        scripts.awsenv-callerident.exec = lib.mkDefault ''
          exec awsenv-aws sts get-caller-identity
        '';
        env = let
          manage_profiles = if cfg.manage-profiles then {
            DEVENV_AWSENV_MANAGE_PROFILES = lib.mkDefault "1";
          } else {};
        in
          {
            DEVENV_AWSENV_TEMPLATE = lib.mkDefault ./template.json;
            DEVENV_AWSENV_PROFILE = cfg.profile;
          } // manage_profiles;

        enterShell = lib.mkBefore ''
          awsenv auth && \
          eval "$(awsenv export)" && \
          echo "⏹️  AWS vars set for $DEVENV_AWSENV" || \
          echo "⏹️  Did not export AWS vars"
        '';
      };
}
