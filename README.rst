=============================================================================
 ``devenv-awsenv``: A tool to help with multiple AWS identities within devenv
=============================================================================

Overview
--------

``devenv-awsenv`` is a devenv plugin that lets you create an arbitrary number
of AWS "environments", each of which can have a different set of AWS
credentials, a different AWS account id, a different region, etc.

It is useful if you use different identities to authenticate to, for example,
your development AWS setup vs. your production AWS setup. It is also useful if
you are a consultant with multiple customers, and you need to switch between
collections of customer AWS resources easily.

It keeps all of its settings in the system keychain of whatever computer you
install it on.  It will work on most Linux systems that have a desktop
environment and on MacOS.  It will not work on headless Linux systems at the
moment.

It handles MFA authentication, and will prompt you for a code whenever
necessary. Alternately, it allows you to provide the environment with an MFA
OTP authentication secret such that you are never asked for the code; the
system will generate MFA codes for you instead (see "Obtaining Your OTP MFA
Authenticator Secret" below).

Enviroment settings are shared between terminals and windows, so you won't need
to rerun MFA authentication for every shell you start.

It also optionally manages AWS profiles in ``~/.aws`` related to each environment.

There is a YouTube video at https://youtu.be/LObkm7Ay08o showing its usage.

Setting It Up
-------------

To enable ``devenv-awsenv`` within a devenv project, you must add its URL to
``devenv.yaml``.  For example, a ``devenv.yaml`` might look like:

.. code-block:: yaml

   inputs:
     nixpkgs:
       url: github:NixOS/nixpkgs/nixpkgs-unstable
     devenv-awsenv:
       url: path:/home/chrism/projects/devenv-awsenv

Then you have to include its plugin and enable it within ``devenv.nix``.  For
example:

.. code-block:: nix

   { pkgs, lib, config, inputs, devenv-awsenv, ... }:

   {
     imports = [ devenv-awsenv.plugin ];

     awsenv.enable = true;
     awsenv.manage-profiles = false;
     awsenv.package = pkgs.awscli2;

   }

Once it is enabled, each time ``devenv shell`` starts, it will attempt to add
environment variables to the shell environment related to AWS.  Tools like aws'
CLI are willing to use these environment values instead of attempting to use a
profile from ``~/.aws`` (unless you have a global ``AWS_PROFILE`` envvar set).

It will also attempt to authenticate with AWS using the default environmment
settings at shell startup time.

The first time you start it, it will inject empty values into the shell's
environment.  It won't be useful until you configure it.  While in the devenv
shell, you can configure it for your use:

.. code-block::

   awsenv edit

This will pull up your ``EDITOR`` and place the current awsenv environment JSON
into its buffer.  Change the values to suit you.  Once you've saved the buffer,
it will write the values into your computer's keychain.

You can then either restart the shell or follow the prompts to activate the
changes.

``devenv-awsenv`` attempts to manage these environment variables:

.. code-block::

   AWS_ACCESS_KEY_ID
   AWS_ACCOUNT_ID
   AWS_DEFAULT_OUTPUT
   AWS_DEFAULT_REGION
   AWS_SECRET_ACCESS_KEY
   AWS_SESSION_EXPIRES
   AWS_SESSION_TOKEN
   DEVENV_AWSENV

It will also set as environment variables any additional keys that you add to
the JSON structure when you edit it.  When you use ``devenv-awsenv``, any
matching envvars inherited from your parent shell will be clobbered.

Don't add ``AWS_SESSION_*`` envvars or ``DEVENV_AWSENV`` to your environment
config when you edit, these will be clobbered too.

It will also manage the ``AWS_PROFILE`` envvar and create accounts with
settings and credentials in ``~/.aws`` related to each environment used if
configured to do so via ``awsenv.manage-profiles`` in ``devenv.nix`` (some
tools don't support using e.g. ``AWS_SECRET_ACCESS_KEY`` and friends as
environment variables direcly and can only cope with ``AWS_PROFILE``).

The default environment is named ``dev``.  You can create a new environment
named ``another`` via:

.. code-block::

   awsenv copy dev another

You can then run:

.. code-block::

   awsenv edit another

To make changes suitable for that new environment.

To make an environment other than "dev" your default environment, run e.g.:

.. code-block::

   awsenv switch another

Note that awsenv environments are not local to a specific devenv environmnent or directory or anything,
they are shared by all devenv environments that you use on the system.

``awsenv`` also has some other features explained in its help:

.. code-block::

   usage: awsenv [-h] {edit,auth,switch,list,delete,copy,export,mfaleft} ...

   awsenv

   positional arguments:
     {edit,auth,switch,list,delete,copy,export,mfaleft}
                           No arguments means show current default awsenv
       edit                Edit an environment
       auth                Supply authentication values (e.g. for MFA) if neccesary
       switch              Make an environment the default
       list                Show all available environments
       delete              Delete an environment
       copy                Copy an environment
       export              Output shell commands to export the required envvars
       mfaleft             Show how much time remains in current MFA session (hh:mm)

   options:
     -h, --help            show this help message and exit

What Gets Installed
-------------------

``devenv-awsenv`` does not install any AWS CLI or related tools for your use.
The only command it exposes is ``awsenv``.  You can use whatever AWS tools you
like, but you'll need to install them yourself in ``devenv.nix``.

If Your MFA Token Expires
-------------------------

You can either run this command::

  awsenv auth && eval "$(awsenv export)"

Or exit the devenv shell and start it again.

Obtaining Your MFA Device Name
------------------------------

It's in the "Security Credentials" settings of the user that you're using to
access a given AWS account.  You may have more than one, and they will differ
between accounts.  This should be placed in ``DEVENV_ASWENV_MFA_DEVICE`` as
you're editing the configuratiom if you use MFA.
   
Obtaining Your OTP MFA Authenticator Secret (Optional)
--------------------------------------------------------

Optionally knowing your OTP authenticator secret for an AWS account allows you
to do automatic MFA authentication when using ``devenv shell`` without needing
to type OTP codes.  ``awsenv edit`` will ask you for the OTP authenticator
secret as ``DEVENV_AWSENV_MFA_OTP_AUTHSECRET`` in the default JSON structure.

The OTP authenticator secret is the secret you use for a given AWS account that
is implied by the "MFA Device" you set up within AWS to gain access initially
to that account.

The easiest way to get your OTP authenticator secret is to set up a new MFA
device in AWS.  When you do, you are prompted with a "show secret" link on the
page with a QR code.

Some of us probably use Google Authenticator as an MFA device.  This app does
not appear to allow you to see this value directly.  Instead, you will need to
export the secret via a QR code generated by the export feature of Google
Authenticator (available in the hamburger menu) into something that does.

`Bitwarden Authenticator <https://bitwarden.com/help/bitwarden-authenticator/>`_
is one such application.  Like Google Authenticator, it runs as an app on iOS
and Android.

To import your existing Google Authenticator code to Bitwarden Authenticator,
use Bitwarden Authenticator's `Google Authenticator QR code import feature
<https://bitwarden.com/help/authenticator-import-export/>`_ against Google
Authenticator's QR code export.  You really only need to export your
account from Google Authenticator, it is the only code that the development
environment is concerned with.

Once you've got the codes imported into Bitwarden Authenticator, you can see
your OTP Authenticator Secret for a given AWS account via its
`JSON export <https://bitwarden.com/help/authenticator-import-export/>`_ feature.  It will
be the "secret" part of the "totp" shown within the "login" dictionary" of the
resulting JSON.

Bitwarden Authenticator also can do the same thing for LastPass QR code
exports, and several others, although I don't know that these don't have their
own JSON or other textual imports that could do the same without needing to
import your codes into Bitwarden Authenticator.

If you'd rather not use Bitwarden Authenticator,
https://github.com/scito/extract_otp_secrets may be useful.  This is a Python
application that can either scan a Google Authenticator QR code via a camera or
can import it via a screenshotted image of the QR code.  The output of the
application will contain the secret for each exported site, including the one
for the AWS account you care about.
