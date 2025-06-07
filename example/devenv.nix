{ pkgs, lib, config, inputs, ... }:

{
  imports = [ ../default.nix ];

  awsenv.enable = true;

  enterShell = ''
    eval "$(awsenv export)"
  '';
}
