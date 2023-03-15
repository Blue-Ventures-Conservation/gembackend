import os

cliprj = 'gem-project-378721'
cliusr = 'projects/gem-project-378721/assets/users/{uid}'
clicmd = 'bin/earthengine --service_account_file={sa_file} {cmd}'
aliexists = 'already exists.'

def cli_create_user_dir(sa_file: str, uid: str) -> bool:
    
    stream = os.popen()
