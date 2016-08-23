import hashlib
import os
import sys
import time

import httplib2
import oauth2client
import apiclient
from googleapiclient.errors import HttpError
from oauth2client import client
from oauth2client import tools
from mimetypes import MimeTypes

from os import walk

# global variables

CREDENTIALS_FILE = "mycreds.txt"
APP_NAME = "GRIVE Client"
CLIENT_SECRET_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

# LINUX
# INSTALL = "/home/Mabez/Computing/GDRIVE/" # These two need to change
# SYNC_FOLDER = "/home/Mabez/Documents/SYNC/"

# WINDOWS
# SYNC_FOLDER = "C:/Users/Mabez/Documents/GDRIVE/files/"
# INSTALL  = "C:/Users/Mabez/Documents/GDRIVE/"

# MAC
SYNC_FOLDER = "/Users/Mabez/Documents/Synced/"
INSTALL = "/Users/Mabez/Documents/GDRIVE/"

RES_FOLDER = INSTALL + "res/"
DB_HOME = RES_FOLDER + "db/"
DB_FILE = DB_HOME + "filedb.db"
CONFIG = RES_FOLDER + "config.ini"


class Authorization:
    def __init__(self):
        self.store = None
        self.credentials = self.loadCredentials()
        self.initializeDriveService()

    def loadCredentials(self):
        store = oauth2client.file.Storage(CREDENTIALS_FILE)
        self.credentials = store.get()
        if not self.credentials or self.credentials.invalid:
            flow = client.flow_from_clientsecrets(CLIENT_SECRET_FILE, SCOPES)
            flow.user_agent = APP_NAME
            self.credentials = tools.run_flow(flow, store, None)
            print('Storing credentials to ' + CREDENTIALS_FILE)
        elif self.credentials.access_token_expired:
            print("Credentials are expired. Attempting to refresh...")
            try:
                self.credentials.refresh()
            except Exception, e:
                print("Refresh failed.")
                print e
        else:
            print("Found credentials in " + CREDENTIALS_FILE)
        return self.credentials

    def initializeDriveService(self):
        http = httplib2.Http()
        http = self.credentials.authorize(http)
        global DRIVE_SERVICE
        DRIVE_SERVICE = apiclient.discovery.build("drive", "v2", http=http)


class FileManagement:
    def __init__(self):
        # create sync_folder if it doesn't exist
        if not self.folderExists(SYNC_FOLDER):
            self.makeDirectory(SYNC_FOLDER)
        self.workingDirectory = SYNC_FOLDER
        self.currentDriveFolder = 'root'
        self.Downloaded = 0
        self.totalFiles = 0
        self.filesDownloaded = 0
        self.filesUploaded = 0
        self.filesOverwritten = 0
        self.mime = MimeTypes()
        # initialize database
        self.dataBase = DataBaseManager()
        global LOCAL_FILE_REMOVED
        LOCAL_FILE_REMOVED = []
        global LOCAL_FILE_ADDED
        LOCAL_FILE_ADDED = []

    def downloadAll(self):
        self.downloadAllFromFolder("root")

    def getFileList(self, folderId):
        return DRIVE_SERVICE.files().list(q="'{0}' in parents and trashed=false".format(folderId)).execute().get(
            'items', [])

    # Currently unused
    def downloadAllFromFolder(self, folderId):
        file_list = self.getFileList(folderId)
        self.totalFiles += len(file_list)
        print(file_list)
        for doc in file_list:
            if "application/vnd.google-apps." in doc['mimeType']:
                if not doc['mimeType'] == "application/vnd.google-apps.folder":
                    self.downloadGDriveFile(doc, self.workingDirectory)
                else:
                    path = str(self.workingDirectory + doc['title'] + "/")
                    if not self.folderExists(path):
                        self.totalFiles -= 1
                        self.makeDirectory(path)
                        self.setWorkingDirectory(path)
                        self.downloadAllFromFolder(doc['id'])
            else:
                self.downloadFile(doc, self.workingDirectory, doc['mimeType'])
        self.setWorkingDirectory(SYNC_FOLDER)  # return to root

    def cloudSyncAll(self, folderId):
        file_list = self.getFileList(folderId)
        for doc in file_list:
            if "application/vnd.google-apps." in doc['mimeType']:
                if not doc['mimeType'] == "application/vnd.google-apps.folder":
                    pass
                    # not sure howto organize gdoc files as of yet
                    # only need add or remove stuff
                else:
                    path = str(self.workingDirectory + doc['title'] + "/")
                    if not self.folderExists(path):
                        self.makeDirectory(path)

                    # Add folder to database
                    if not self.dataBase.isInDataBase(doc['id']):
                        self.dataBase.addToDataBase(doc, path)

                    self.totalFiles -= 1
                    self.setWorkingDirectory(path)
                    self.currentDriveFolder = doc['id']
                    self.cloudSyncAll(doc['id'])
            else:
                self.cloudSync(doc)

        self.currentDriveFolder = 'root'
        paths = self.workingDirectory.split("/")
        prevPath = ""
        for i in range((len(paths) - 2)):
            prevPath += paths[i] + "/"
        if not self.workingDirectory == SYNC_FOLDER:
            self.setWorkingDirectory(prevPath)

    def localSyncAll(self, path):
        # for file in sync folder check if file is in db if not upload it and add id's and checksums to db
        # if file is folder call this function again recursively till be have checked all
        for (dirpath, dirnames, filenames) in walk(path):
            if dirpath is SYNC_FOLDER:
                # Sync folder will not have a id but when we upload not using an id it will go to root
                for file in filenames:
                    # check file is not a hidden one
                    if not file.startswith("."):
                        self.localSync(SYNC_FOLDER + file)
            else:
                # print "Folder at ", dirpath, "has id: ", self.dataBase.getIdFromPath(dirpath+ os.sep)
                # Todo
                # If folder is not in database, insert a folder on drive a add that to the database
                for file in filenames:
                    if not file.startswith("."):
                        self.localSync(dirpath + os.sep + file)

    def createFolderInDrive(self, title):
        # need to implement this properly
        folder = DRIVE_SERVICE.CreateFile(
            {'title': '{0}'.format(title), 'mimeType': 'application/vnd.google-apps.folder',
             "parents": [{"kind": "drive#fileLink", "id": self.currentDriveFolder}]})
        folder.Upload()

    def setWorkingDirectory(self, path):
        self.workingDirectory = path

    def downloadFile(self, fileMeta, folder):
        fullPath = folder + fileMeta['title']
        if not self.folderExists(folder):
            self.makeDirectory(folder)
        # print("Downloading {0} with id {1}".format(fileMeta['title'],fileMeta['id']))
        print("Downloading From Drive: ", fileMeta['title'])
        fileDownload = fileMeta.get('downloadUrl')
        if fileDownload:
            resp, content = DRIVE_SERVICE._http.request(fileDownload)
            if resp.status == 200:
                print('Status: %s' % resp)
            f = open(fullPath, "w")  # write content to file
            f.write(content)
            f.close()
        else:
            print("Error downloading file. No content detected.")
        # add to data base
        self.dataBase.addToDataBase(fileMeta, fullPath)
        # increase tally
        self.Downloaded += 1

    def downloadGDriveFile(self, fileMeta, folder):
        fullPath = folder + fileMeta['title'] + ".desktop"
        shortcutImg = RES_FOLDER + "doc.png"
        end = "\n"
        if not self.folderExists(folder):
            self.makeDirectory(folder)
        if not self.fileExists(fullPath):
            f = open(fullPath, "w")
            f.write("[Desktop Entry]" + end)
            f.write("Encoding=UTF-8" + end)
            f.write("Name=" + fileMeta['title'] + end)
            f.write("Type=Link" + end)
            f.write("URL=" + fileMeta['alternateLink'] + end)
            f.write("Icon=" + shortcutImg + end)
            f.close()
            self.Downloaded += 1

    @staticmethod
    def folderExists(folder):
        return os.path.isdir(folder)

    @staticmethod
    def fileExists(fileLocation):
        return os.path.isfile(fileLocation)

    @staticmethod
    def makeDirectory(path):
        os.mkdir(path)

    def getLocalMd5(self, fullPath):  # works perfectly returns the same md5s as google's
        if self.fileExists(fullPath):
            return hashlib.md5(open(fullPath, 'rb').read()).hexdigest()
        else:
            print("No File to hash, path: ", fullPath)
            dirs = fullPath.split("/")
            self.removeFromDrive('root', dirs[(len(dirs)) - 1])

    def cloudSync(self, fileMeta):  # not checking folder
        # check if cloud has new file --> initiate download
        # if cloudMd5!=dbmd5 && dbmd5==localmd5 cloud has changed -->
        # initiate overwrite --> update db with new md5 for specific id
        fileID = fileMeta['id']
        title = fileMeta['title']

        if self.fileExists(self.workingDirectory + title):
            if self.dataBase.isInDataBase(fileID):
                storedMd5 = self.dataBase.getMd5(fileID)
                cloudMd5 = fileMeta['md5Checksum']
                local = self.dataBase.getFilePath(fileID)
                if cloudMd5 != storedMd5 and self.getLocalMd5(local) == storedMd5:
                    self.downloadFile(fileMeta, self.workingDirectory)
                    self.dataBase.updateRecord(fileMeta, local)
                    self.filesOverwritten += 1
        else:
            # new file --> download it
            if "application/vnd.google-apps." in fileMeta['mimeType']:
                if not fileMeta['mimeType'] == "application/vnd.google-apps.folder":
                    pass
                    # self.downloadGDriveFile(doc,self.workingDirectory)
                    # not sure what to do with GDoc files yet as they need to be implemented across
                    # platforms
            else:
                self.downloadFile(fileMeta, self.workingDirectory)
                self.filesDownloaded += 1

    def localSync(self, path):
        # Check if path is directory or file
        # Upload file or insert folder accordingly
        parentID = self.dataBase.getIdFromPath(os.path.dirname(path) + os.sep)
        fileID = self.dataBase.getIdFromPath(path)
        if fileID is not None:  # If fileID returns None then it is not in the db
            currentMd5 = self.getLocalMd5(path)
            dbMd5 = self.dataBase.getMd5(fileID)
            if currentMd5 != dbMd5:
                # This file has changed update it!
                print "A change has been detected in ", path
                mimeType = self.mime.guess_type(path)  # Get mimeType from local file
                body = {'parents': [{"id": parentID}]}
                mediaBody = apiclient.http.MediaFileUpload(path, mimeType, resumable=True)
                editedFile = DRIVE_SERVICE.files().update(fileId=fileID, body=body, media_body=mediaBody).execute()
                self.dataBase.updateRecord(editedFile, path)
                self.filesOverwritten += 1

        else:
            # New file detected, upload it here!
            mimeType = self.mime.guess_type(path)  # Get mimeType from local file
            print "A new file detected with mimeType {} here: ".format(mimeType), path
            body = {"title": os.path.basename(path), "mimeType": mimeType, 'parents': [{"id": parentID}]}
            mediaBody = apiclient.http.MediaFileUpload(path, mimeType, resumable=True)
            uploadedMeta = DRIVE_SERVICE.files().insert(body=body, media_body=mediaBody).execute()
            # Replace the meta with a folder that relates to the local files position
            self.dataBase.addToDataBase(uploadedMeta, path)
            self.filesUploaded += 1

    def dataBaseSync(self):
        # check the database for files/folders that have been deleted
        self.dataBase.openFile("r")
        for line in self.dataBase.file:
            # get path, check if it exists, if not remove from cloud
            path = line.split(",")[-1].strip("\n")
            if not os.path.exists(path):
                # File has been removed, renamed or moved
                print "File or directory at: ", path, "no longer exists or has been moved"
                id = self.dataBase.getIdFromPath(path)
                if id is not None:
                    try:
                        DRIVE_SERVICE.files().trash(fileId=id).execute()  # Using trash over delete, just in case
                    except HttpError, err:
                        print err
                    self.dataBase.removeFromDataBase(id)
        self.dataBase.closeFile()


class DataBaseManager:
    def __init__(self):
        if not os.path.exists(DB_HOME):
            os.mkdir(DB_HOME)
        if not os.path.isfile(DB_FILE):
            f = open(DB_FILE, "w")
            f.close()
        self.file = open(DB_FILE, "r")
        self.closeFile()

    def addToDataBase(self, fileMeta, fullPath):
        self.openFile("a+")
        if os.path.isfile(fullPath):
            md5 = str(fileMeta['md5Checksum'])
        else:
            md5 = "NONE"
        string = str(fileMeta['id']) + "," + str(fileMeta['parents'][0]['id']) + "," + md5 + \
                 "," + str(fileMeta['mimeType']) + "," + fullPath + "\n"
        self.file.write(string)
        self.closeFile()

    def isInDataBase(self, fileID):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                return True
        self.closeFile()
        return False

    def openFile(self, mode):
        self.file = open(DB_FILE, mode)

    def closeFile(self):
        self.file.close()

    def updateRecord(self, fileMeta, fullPath):
        # remove it
        self.removeFromDataBase(fileMeta['id'])
        # re-add it with the new md5
        self.addToDataBase(fileMeta, fullPath)

    def getMd5(self, fileID):
        # find md5 in file form id
        # return it
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                return id1[2]
        self.closeFile()

    def getFilePath(self, fileID):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                return id1[4].strip("\n")
        self.closeFile()

    # Can be used to get parent folder id's (Needs testing)
    def getIdFromPath(self, fullPath):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[4].strip("\n") == fullPath:
                return id1[0]
        self.closeFile()

    def getParentsFromId(self, fileId):
        self.openFile("r")
        for line in self.file:
            data = line.split(",")
            if data[0] == fileId:
                return data[1]

    def getMimeTypeFromPath(self, path):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[4].strip("\n") == path:
                return id1[3]
        self.closeFile()

    def removeFromDataBase(self, fileID):
        self.openFile("r+")
        lines = self.file.readlines()
        self.file.seek(0)
        for line in lines:
            if fileID not in line:  # if id is NOT in line then write it
                self.file.write(line)
        self.file.truncate()  # remove the extras
        self.closeFile()


def run():
    GA = Authorization()
    GA.initializeDriveService()
    FM = FileManagement()
    while 1:
        try:
            start = time.time()
            FM.dataBaseSync()
            # Run cloud sync on another thread and only sync every 5 mins or so
            # FM.cloudSyncAll('root')
            FM.localSyncAll(SYNC_FOLDER)
            end = time.time()
            print('Sync Complete in {:.2f} seconds . {} new files downloaded.'
                  ' {} new files uploaded. {} files updated.'.format(
                (end - start), FM.filesDownloaded, FM.filesUploaded, FM.filesOverwritten))
            FM.filesDownloaded = 0
            FM.filesUploaded = 0
            FM.filesOverwritten = 0
            # time.sleep(5)
        except KeyboardInterrupt:
            break
        finally:
            FM.dataBase.closeFile()


if __name__ == "__main__":  # load settings like filepath etc, if its not there use add sys arguments to determine sync folder etc
    arguments = sys.argv
    print(arguments)
    if len(arguments) > 1:
        sync = arguments[1]
        print('Arguments given: ', sync)
        print('This argument will change the sync path')
    run()
    # GA = Authorization()
    # GA.initializeDriveService()
    # FM = FileManagement()
    # FM.localSyncAll(SYNC_FOLDER)
