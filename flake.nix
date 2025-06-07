{
  description = "devenv-awsenv";

  inputs = {};

  outputs = { self }:
    {
      moduledir = builtins.dirOf __curPos.file;
      plugin = (import ./default.nix { inherit self;} );
    };
}
