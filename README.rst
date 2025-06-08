``devenv-awsenv``: A tool to help with multiple AWS identies within devenv
==========================================================================

.. code-block::

   usage: awsenv.py [-h] {edit,auth,switch,list,delete,copy,export,mfaleft} ...

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
       mfaleft             Show how much time is left in the current MFA session (hh:mm)

   options:
     -h, --help            show this help message and exit
   
