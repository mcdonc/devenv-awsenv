{ pkgs, lib, config, inputs, devenv-awsenv, ... }:

{
  imports = [ devenv-awsenv.plugin ];

  awsenv.enable = true;

  env = {
    EDITOR = "emacs -nw";
  };

}
