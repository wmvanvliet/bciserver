@echo off
REM Script that checks for the presence of needed depandancies and installs them
REM if necessary.
REM
REM Marijn van Vliet <marijn.vanvliet@med.kuleuven.be>

echo Some dependencies need to be downloaded from the POOL.
echo For the questions below, you can hit enter to accept the [default value].

set hostname=siren.neuro.kuleuven.be
set username=
set pooldir=/data/data2_solaris/pool

:questions
set /P i_hostname=Hostname of a server that has access to the POOL [%hostname%]: 
IF NOT [%i_hostname%] == [] set hostname=%i_hostname%

set /P i_username=Username to access the server specified above [%username%]: 
IF NOT [%i_username%] == [] set username=%i_username%

set /P i_pooldir=Absolute path to the POOL [%pooldir%]:
IF NOT [%i_pooldir%] == [] set pooldir=%i_pooldir%

set git_url=git+ssh://%username%@%hostname%%pooldir%
echo The URL to be used is: %git_url%

:correct
set /P correct=Is this correct? (Y/N)
IF /I %correct% == n goto :questions
IF /I %correct% == y goto :install
goto :correct

:install
REM Using PIP to install dependencies

pip install -q -r requirements.txt
pip install -q %git_url%/EEG-BCI/git/golem@marijn#egg=golem
pip install -q %git_url%/EEG-BCI/git/psychic@marijn#egg=psychic
pip install -q %git_url%/EEG-BCI/git/pyepoc@marijn#egg=pyepoc

echo Dependencies installed.
