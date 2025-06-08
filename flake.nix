{
  description = "devenv-awsenv";

  inputs = {};

  outputs = { self }:
    {
      plugin = (import ./default.nix);
    };
}
