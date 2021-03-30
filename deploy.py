import os
import argparse
import requests
import json
import re

DROPBOX_ERROR_CODE = 1
TEMPLATE_ERROR_CODE = 2
CHANGES_ERROR_CODE = 3
OUTPUT_FILE_PARSING_ERROR = 4
TELEGRAM_ERROR_CODE = 5

DROPBOX_UPLOAD_ARGS = {
    'path': None,
    'mode': 'overwrite',
    'autorename': True,
    'strict_conflict': True
}
DROPBOX_UPLOAD_URL = 'https://content.dropboxapi.com/2/files/upload'

DROPBOX_SHARE_DATA = {
    'path': None,
    'settings': {
        'requested_visibility': 'public'
    }
}
DROPBOX_SHARE_URL = 'https://api.dropboxapi.com/2/sharing/create_shared_link_with_settings'

DROPBOX_DELETE_DATA = {
    'path' : None
}
DROPBOX_DELETE_URL = 'https://api.dropboxapi.com/2/files/delete_v2'

def upload_to_dropbox(file_name, file, dropbox_token, dropbox_folder):
    ''' Upload file to dropbox.
    Args:
        file_name (str): Rename uploaded file.
        file (str): File you want to upload.
        dropbox_token (str): Dropbox Access Token.
        dropbox_folder (str): Dropbox target folder.
    Returns
        str: Downloaded url.
    '''
    dropbox_path = '/{folder}/{file_name}'.format(folder=dropbox_folder, file_name=file_name)
    DROPBOX_UPLOAD_ARGS['path'] = dropbox_path
    DROPBOX_SHARE_DATA['path'] = dropbox_path
    DROPBOX_DELETE_DATA['path'] = dropbox_path

    # Delete current file
    headers = {'Authorization': 'Bearer ' + dropbox_token,
            'Content-Type': 'application/json'}
    
    requests.post(DROPBOX_DELETE_URL, data=json.dumps(DROPBOX_DELETE_DATA), headers=headers)

    # Upload file
    headers = {'Authorization': 'Bearer ' + dropbox_token,
               'Dropbox-API-Arg': json.dumps(DROPBOX_UPLOAD_ARGS),
               'Content-Type': 'application/octet-stream'}
    
    r = requests.post(DROPBOX_UPLOAD_URL, data=open(file, 'rb'), headers=headers)

    if r.status_code != requests.codes.ok:
        #show error code and error content
        print("Upload failed, code: {errcode}".format(errcode=r.status_code))
        print("Content {content}".format(content=r.content))
        return None
    
    # Share and get download url
    headers = {'Authorization': 'Bearer ' + dropbox_token,
               'Content-Type': 'application/json'}

    r = requests.post(DROPBOX_SHARE_URL, data=json.dumps(DROPBOX_SHARE_DATA), headers=headers)

    if r.status_code != requests.codes.ok:
        print("Get url failed, code: {errcode}".format(errcode=r.status_code))
        print("Content {content}".format(content=r.content))
        return None

    # Replace the '0' at the end of the url with '1' for direct download
    return re.sub('dl=.*', 'raw=1', r.json()['url'])

def get_app(app_dir):
    '''Extract app data
    Args:
        dir (str): Directory path.
    
    Returns:
        (str, str): App version and path app file.
    '''
    # Get output.json file to get info about app
    output_path = os.path.join(app_dir, 'output.json')

    with(open(output_path)) as app_output:
        json_data = json.load(app_output)

    apk_details_key = ''

    #multiple build flavor, because i can't get real versionName in output.json flavor
    if 'elements' in json_data:
        outputFile = json_data['elements'][0]['outputFile']
        app_version = outputFile.split('_')[1].replace('-', '.')
        app_file = os.path.join(app_dir, outputFile)
    elif 'apkInfo' in json_data[0]:
        apk_details_key = 'apkInfo'
        app_version = json_data[0][apk_details_key]['versionName']
        app_file = os.path.join(app_dir, json_data[0][apk_details_key]['outputFile'])
    elif 'apkData' in json_data[0]:
        apk_details_key = 'apkData'
        app_version = json_data[0][apk_details_key]['versionName']
        app_file = os.path.join(app_dir, json_data[0][apk_details_key]['outputFile'])
    else:
        print("Failed: parsing json in output file")
        return None, None

    return app_version, app_file

def get_rename_file_name(app_name, app_version):
    '''Get renamed file name for app.
    example:
    app_name - WowApp
    version - 1.0.0
    result: wowapp_1_0_0.apk
    Args:
        app_name (str): App name.
        app_version (str): App version.
    Returns:
        str: Renamed app file name.
    '''
    app_name = app_name.lower()
    app_version = app_version.replace('.', '_')
    return '{name}_{version}.apk'.format(name=app_name, version=app_version).replace(' ','')

def get_changes(change_log_path):
    '''Extract latest changes from changelog file.
    Changes are separated by ##
    Args:
        change_log_path (str): Path to changelog file.
    Returns:
        str: Latest changes.
    '''
    with(open(change_log_path)) as change_log_file:
        change_log = change_log_file.read()

    # Split by '##' and remove lines starting with '#'
    latest_version_changes = change_log.split('##')[0][:-1]
    latest_version_changes = re.sub('^#.*\n?', '', latest_version_changes, flags=re.MULTILINE)

    return latest_version_changes

def get_message(app_name, app_version, app_url, changelog, template_file):
    '''Use template file to create message.
    You must add name, version, url, and changelog parameter in your template file.
    Args:
        app_name (str): App name.
        app_version (str): App version.
        app_url (str): Url download app. 
        changelog (str): Lastest app changelog.
        template_file (str): Path to template file.
    
    Returns:
        (str): Message text
    '''
    template = ''
    message = ''

    with(open(template_file)) as template_file:
        # Open template file and replace placeholders with data
        template = template_file.read().format(
            app_download_url=app_url,
            change_log=changelog,
            app_name=app_name,
            app_version=app_version
        )
    
    for line in template.splitlines():
        message += line + '\n'
    
    return message

def send_message_telegram(bot_code, chat_id, app_name, file_url, message):
    ''' Send message bot to chat.
    Args:
        bot_code (str): Bot Code Telegram.
        chat_id (str): Chat ID Telegram.
        app_name (str): App Name.
        file_url (str): Url File.
        message (str): Message you want to send.
    
    Returns:
        bool: Send success/fail.
    '''

    url_request = 'https://api.telegram.org/bot{bot_code}/sendMessage?chat_id={chat_id}&text={message}'.format(bot_code=bot_code, chat_id=chat_id, message=message)

    r = requests.get(url_request)

    return r.status_code == requests.codes.ok

if __name__ == '__main__':
    # Command line arguments
    parser = argparse.ArgumentParser()
    parser.add_argument('--release.dir', dest='release_dir', help='path to release folder', required=True)
    parser.add_argument('--app.name', dest='app_name', help='app name that will be used as file name', required=True)
    parser.add_argument('--changelog.file', dest='changelog_file', help='path to changelog file', required=True)
    parser.add_argument('--template.file', dest='template_file', help='path to email template file', required=True)
    parser.add_argument('--dropbox.token', dest='dropbox_token', help='dropbox access token', required=True)
    parser.add_argument('--dropbox.folder', dest='dropbox_folder', help='dropbox target folder', required=True)
    parser.add_argument('--bot.code', dest='bot_code', help='bot code telegram', required=True)
    parser.add_argument('--bot.chat_id', dest='chat_id', help='chat id telegram', required=True)

    options = parser.parse_args()

    # Extract app version and file
    app_version, app_file = get_app(options.release_dir)
    if app_version == None or app_file == None:
        exit(OUTPUT_FILE_PARSING_ERROR)
    
    target_app_file = get_rename_file_name(options.app_name, app_version)

    # Upload app file and get shared url
    file_url = upload_to_dropbox(target_app_file, app_file, options.dropbox_token, options.dropbox_folder)
    if file_url == None:
        exit(DROPBOX_ERROR_CODE)
    
    # Extract latest changes
    latest_changes = get_changes(options.changelog_file)
    if latest_changes == None:
        exit(CHANGES_ERROR_CODE)
     
    # Send message to telegram
    message = get_message(options.app_name, app_version, file_url, latest_changes, options.template_file)
    if not send_message_telegram(options.bot_code, options.chat_id, options.app_name, file_url, message):
        exit(TELEGRAM_ERROR_CODE)
