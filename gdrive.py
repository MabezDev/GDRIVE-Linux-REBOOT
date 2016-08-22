import hashlib
import os
import sys
import time

import httplib2
import oauth2client
import apiclient
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
            except Exception:
                print("Refresh failed.")
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
                    self.totalFiles -= 1
                    self.setWorkingDirectory(path)
                    self.currentDriveFolder = doc['id']
                    self.cloudSyncAll(doc['id'])
            else:
                self.cloudSync(doc)

        self.currentDriveFolder = 'root'
        paths = self.workingDirectory.split("/")
        self.prevPath = ""
        for i in range((len(paths) - 2)):
            self.prevPath += paths[i] + "/"
        if not self.workingDirectory == SYNC_FOLDER:
            self.setWorkingDirectory(self.prevPath)

    def localSyncAllOld(self, folderId):
        #
        #   This should be redone to check the database no the cloud, as we sync cloud first we will always have the
        #   most up to date data
        #
        file_list = self.getFileList(folderId)
        for doc in file_list:
            if "application/vnd.google-apps." in doc['mimeType']:
                if not doc['mimeType'] == "application/vnd.google-apps.folder":
                    pass
                    # not sure howto organize gdoc files as of yet
                    # create folder on drive
                    # set working directory to this path
                else:
                    path = str(self.workingDirectory + doc['title'] + "/")
                    if not self.folderExists(path):
                        self.makeDirectory(path)
                    self.totalFiles -= 1
                    self.setWorkingDirectory(path)
                    self.currentDriveFolder = doc['id']

                    # folders not working needs to be redeveloped
                    # self.checkFolders()

                    self.localSyncAll(doc['id'])
            else:
                self.localSync(doc)

        self.currentDriveFolder = 'root'
        paths = self.workingDirectory.split("/")
        self.prevPath = ""
        for i in range((len(paths) - 2)):
            self.prevPath += paths[i] + "/"
        if not self.workingDirectory == SYNC_FOLDER:
            self.setWorkingDirectory(self.prevPath)

    def localSyncAll(self,path):
        # for file in sync folder check if file is in db if not upload it and add id's and checksums to db
        # if file is folder call this function again recursively till be have checked all
        for (dirpath, dirnames, filenames) in walk(path):
            for file in filenames:
                # check file is not a hidden one
                if not file.startswith("."):
                    if dirpath is SYNC_FOLDER:
                        self.localSync(SYNC_FOLDER+file)
                    else:
                        self.localSync(dirpath + os.sep + file)

    def createFolderInDrive(self, title):
        # need to implement this properly
        folder = DRIVE_SERVICE.CreateFile(
            {'title': '{0}'.format(title), 'mimeType': 'application/vnd.google-apps.folder',
             "parents": [{"kind": "drive#fileLink", "id": self.currentDriveFolder}]})
        folder.Upload()

    def setWorkingDirectory(self, path):
        self.workingDirectory = path

    def downloadFile(self, fileMeta, folder, mimeType):
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
        self.dataBase.addToDataBase(fileMeta['id'], fileMeta['md5Checksum'], fullPath)
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

    def getLocalMd5(self, fullPath):  # works perfectly returns the same md5s as googles
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
                    # print("Overwriting Local File :",doc['title'])#overwriting from cloud
                    self.downloadFile(fileMeta, self.workingDirectory, fileMeta['mimeType'])
                    self.dataBase.updateRecord(fileID, cloudMd5, local)
                    self.filesOverwritten += 1
        else:
            # new file --> download it
            if "application/vnd.google-apps." in fileMeta['mimeType']:
                if not fileMeta['mimeType'] == "application/vnd.google-apps.folder":
                    pass
                    # self.downloadGDriveFile(doc,self.workingDirectory)
                    # not sure what to do with GDoc files yet
            else:
                self.downloadFile(fileMeta, self.workingDirectory, fileMeta['mimeType'])
                self.filesDownloaded += 1

    def checkFolders(self):  # check folders not working properly
        folders = os.walk(self.workingDirectory)
        for folder in folders:
            print("Folder is: ", folder[0])
            if folder[0] == SYNC_FOLDER:
                continue
            if os.path.isdir(folder[0]):
                # print("Checking if '{0}' is in drive.".format(folder[0]))
                dirs = folder[0].split("/")
                print("Dirs: ", dirs)
                index = 1
                fileName = dirs[(len(dirs) - index)]
                while fileName == '':
                    fileName = dirs[len(dirs) - index]
                    index += 1
                print(fileName)
                if not self.isInDrive(self.currentDriveFolder, fileName):
                    print("Creating folder in drive called: ", fileName)
                    # self.createFolderInDrive(fileName)


    # change this (below) to reflect the new localSyncAll proper code (local only)
    def localSyncOld(self, fileMeta):
        fileID = fileMeta['id']
        fileCheckSum = fileMeta['md5Checksum']
        title = fileMeta['title']
        # if local!= db && db==cloud (this is always true as we sync cloud first! So we do not have to
        # check cloud at all!) --> local has changed -->
        # iniate upload(overwrite) to drive --> update db with new md5 for specific id
        if self.dataBase.isInDataBase(fileID):
            path = self.dataBase.getFilePath(fileID)
            localmd5 = self.getLocalMd5(path)
            dbmd5 = self.dataBase.getMd5(fileID)
            # print("DBMD5: {0} LOCALMD5: {1} CLOUDMD5: {2}".format(dbmd5,localmd5,fileCheckSum))
            if (localmd5 != dbmd5) and (str(fileCheckSum) == dbmd5):
                # overwrite online
                print('File md5 has changed at : ', path)
                if self.fileExists(path):
                    mediaBody = apiclient.http.MediaFileUpload(path, fileMeta["mimeType"], resumable=True)
                    DRIVE_SERVICE.files().update(fileId=fileID, media_body=mediaBody).execute()
                    self.dataBase.updateRecord(fileID, localmd5, path)
                    self.filesOverwritten += 1
                else:
                    print(title, " doesnt exists!")
                    self.dataBase.removeFromDataBase(fileID)

    def localSync(self,path):
        fileID = self.dataBase.getIdFromPath(path)
        if fileID is not None:  # If fileID returns None then it is not in the db
            currentMd5 = self.getLocalMd5(path)
            dbMd5 = self.dataBase.getMd5(fileID)
            if currentMd5 != dbMd5:
                # This file has changed update it!
                print "A change has been detected in ", path
                mimeType = self.mime.guess_type(path)  # Get mimeType from local file
                mediaBody = apiclient.http.MediaFileUpload(path, mimeType, resumable=True)
                DRIVE_SERVICE.files().update(fileId=fileID, media_body=mediaBody).execute()
                self.dataBase.updateRecord(fileID, currentMd5, path)
                self.filesOverwritten += 1

        else:
            # New file detected, upload it here!
            mimeType = self.mime.guess_type(path) # Get mimeType from local file
            print "A new file detected with mimeType {} here: ".format(mimeType), path
            body = {"title": os.path.basename(path), "mimeType": mimeType}  # add parent when we have support for it
            mediaBody = apiclient.http.MediaFileUpload(path, mimeType, resumable=True)
            uploadedMeta = DRIVE_SERVICE.files().insert(body=body, media_body=mediaBody).execute()
            self.dataBase.addToDataBase(uploadedMeta['id'], uploadedMeta['md5Checksum'], path)
            self.filesUploaded += 1


# TODO for database, add mimeType Storage, with that add folder support, so we can upload files into there correct place
class DataBaseManager:
    def __init__(self):
        if not os.path.exists(DB_HOME):
            os.mkdir(DB_HOME)
        if not os.path.isfile(DB_FILE):
            f = open(DB_FILE, "w")
            f.close()
        self.file = open(DB_FILE, "r")
        self.closeFile()

    def addToDataBase(self, fileID, md5, fullPath):
        self.openFile("a+")
        string = str(fileID) + "," + str(md5) + "," + fullPath + "\n"
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

    def updateRecord(self, fileID, newMd5, fullPath):
        # remove it
        self.removeFromDataBase(fileID)
        # re-add it with the new md5
        self.addToDataBase(fileID, newMd5, fullPath)

    def getMd5(self, fileID):
        # find md5 in file form id
        # return it
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                return id1[1]
        self.closeFile()

    def getFilePath(self, fileID):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                return id1[2].strip("\n")
        self.closeFile()

    def getIdFromPath(self, fullPath):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[2].strip("\n") == fullPath:
                return id1[0]
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
            FM.cloudSyncAll('root')
            FM.localSyncAll('root')
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
    # run()
    GA = Authorization()
    GA.initializeDriveService()
    FM = FileManagement()
    FM.localSyncAll(SYNC_FOLDER)
