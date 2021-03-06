import hashlib
import os
import sys
import time
import shutil

import datetime
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
        self.http = httplib2.Http()
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
                self.credentials.refresh(self.http)
            except Exception, e:
                print("Refresh failed.")
                print e
        else:
            print("Found credentials in " + CREDENTIALS_FILE)
        return self.credentials

    def initializeDriveService(self):
        http = self.credentials.authorize(self.http)
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
        self.currentDriveFileList = []
        # initialize database
        self.dataBase = DataBaseManager()
        global LOCAL_FILE_REMOVED
        LOCAL_FILE_REMOVED = []
        global LOCAL_FILE_ADDED
        LOCAL_FILE_ADDED = []

    @staticmethod
    def getFileList(folderId):
        return DRIVE_SERVICE.files().list(q="'{0}' in parents and trashed=false".format(folderId)).execute().get(
            'items', [])

    @staticmethod
    def folderExists(folder):
        return os.path.isdir(folder)

    @staticmethod
    def fileExists(fileLocation):
        return os.path.isfile(fileLocation)

    @staticmethod
    def makeDirectory(path):
        os.mkdir(path)

    def setWorkingDirectory(self, path):
        self.workingDirectory = path

    def getLocalMd5(self, fullPath):  # works perfectly returns the same md5s as google's
        if self.fileExists(fullPath):
            return hashlib.md5(open(fullPath, 'rb').read()).hexdigest()

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
        # increase tally
        self.Downloaded += 1

    # Need to implement this across OS's (this works on fedora currently)
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
                        print "New Folder in drive, id: ", doc['id'], " path: ", path

                    # Add folder to database
                    if not self.dataBase.isInDataBase(doc['id']):
                        self.dataBase.addToDataBase(doc, path)

                    # Add folderId to current drive list
                    self.currentDriveFileList.append(doc['id'])

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

    def cloudSync(self, fileMeta):  # not checking folder
        # check if cloud has new file --> initiate download
        # if cloudMd5!=dbmd5 && dbmd5==localmd5 cloud has changed -->
        # initiate overwrite --> update db with new md5 for specific id
        fileID = fileMeta['id']
        title = fileMeta['title']
        self.currentDriveFileList.append(fileID)
        if self.dataBase.isInDataBase(fileID):
            if self.fileExists(self.workingDirectory + title):
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
                # add to data base
                self.dataBase.addToDataBase(fileMeta, self.workingDirectory + fileMeta['title'])
                self.filesDownloaded += 1

    def localSyncAll(self, path):
        # for file in sync folder check if file is in db if not upload it and add id's and checksums to db
        # if file is folder call this function again recursively till be have checked all
        for (dirpath, dirnames, filenames) in walk(path):
            fixedPath = os.path.join(dirpath, '')
            # Sync folder will not have a id but when we upload not using an id it will go to root
            for file in filenames:
                # check file is not a hidden one
                if not file.startswith("."):
                    self.localSync(fixedPath + file)

            if self.dataBase.getIdFromPath(fixedPath) is None and fixedPath is not SYNC_FOLDER:
                parentFolder = os.path.join(os.path.dirname(os.path.dirname(fixedPath)), '')
                parentID = self.dataBase.getIdFromPath(parentFolder)
                if parentID is None:
                    parentID = 'root'

                print "New folder detected ,", fixedPath, "uploading to ", parentID, " in drive."
                body = {"title": os.path.basename(dirpath),
                        "mimeType": 'application/vnd.google-apps.folder',
                        'parents': [{"id": parentID, "kind": "drive#fileLink"}]}
                folderMeta = DRIVE_SERVICE.files().insert(body=body).execute()
                self.currentDriveFileList.append(folderMeta['id'])
                self.dataBase.addToDataBase(folderMeta, fixedPath)

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
                mimeType, enc = self.mime.guess_type(path)  # Get mimeType from local file
                if mimeType is None:
                    mimeType = "text/plain"
                body = {'parents': [{"id": parentID}]}
                mediaBody = apiclient.http.MediaFileUpload(path, mimeType, resumable=True)
                editedFile = DRIVE_SERVICE.files().update(fileId=fileID, body=body, media_body=mediaBody).execute()
                self.dataBase.updateRecord(editedFile, path)
                self.filesOverwritten += 1

        else:
            # New file detected, upload it here!
            mimeType, enc = self.mime.guess_type(path)  # Get mimeType from local file
            if mimeType is None:
                mimeType = "text/plain"
            print "A new file detected with mimeType {} here: ".format(mimeType), path
            body = {"title": os.path.basename(path), "mimeType": mimeType, 'parents': [{"id": parentID}]}
            mediaBody = apiclient.http.MediaFileUpload(path, mimeType, resumable=True)
            uploadedMeta = DRIVE_SERVICE.files().insert(body=body, media_body=mediaBody).execute()
            self.currentDriveFileList.append(uploadedMeta['id'])
            # Replace the meta with a folder that relates to the local files position
            self.dataBase.addToDataBase(uploadedMeta, path)
            self.filesUploaded += 1

    # check cloud here also, if a file is not in cloud but in db it means it has been deleted/moved/renamed
    def dataBaseSync(self):
        # check the database for files/folders that have been deleted
        self.dataBase.openFile("r")
        for line in self.dataBase.file:
            # get path, check if it exists, if not remove from cloud
            dbLine = line.split(",")
            path = dbLine[-1].strip("\n")
            id = dbLine[0]
            if not os.path.exists(path):
                # File has been removed, renamed or moved
                print "File or directory at: ", path, "no longer exists or has been moved"
                self.dataBase.setDeleted(id)
                try:
                    DRIVE_SERVICE.files().trash(fileId=id).execute()  # Using trash over delete, just in case
                except HttpError, err:
                    print err
                # Add set deleted local to true
                self.dataBase.removeFromDataBase(id)

            # if the current id from the database is NOT in the cloud file list and the local file has not been edited
            #  and self.dataBase.getMd5(id) is self.getLocalMd5(path) # needs testing
            if id not in self.currentDriveFileList:
                print "A file has been deleted from drive, with id: ", id, " , deleting locally at : ", path
                if os.path.exists(path):
                    # Need to handle removing files folders and sub folders
                    # os.remove(path)
                    # print "Removing ", path, " ..."
                    if os.path.isdir(path):
                        shutil.rmtree(path, ignore_errors=True)
                    else:
                        os.remove(path)
                    # Add set deleted cloud to true
                self.dataBase.removeFromDataBase(id)

        self.dataBase.closeFile()

    # DataBase File structure:
    #
    # drive_id, parent_id, md5 hash from drive (NONE if not available), mimeType, localPath
    # Proposed data structure to fix re download problem:
    # drive_id, parent_id, md5 hash from drive (NONE if not available), mimeType,
    #         deletedLocal (true or false), deletedCloud (true or false), localPath
    #
    #   Ideology~
    #
    #   Local: If the path is detected missing, set deleted flag to true
    #   Cloud: If id is missing set false to true
    #   Syncing: check if in db like normal but db sync checks that both are true then removed the record from the db


class DataBaseManager:
    def __init__(self):
        if not os.path.exists(DB_HOME):
            os.mkdir(DB_HOME)
        if not os.path.isfile(DB_FILE):
            f = open(DB_FILE, "w")
            f.close()
        self.file = open(DB_FILE, "r")
        self.closeFile()

    def addToDataBase(self, fileMeta, fullPath, deleted="false"):
        self.openFile("a+")
        if os.path.isfile(fullPath):
            md5 = str(fileMeta['md5Checksum'])
        else:
            md5 = "NONE"
        string = str(fileMeta['id']) + "," + str(fileMeta['parents'][0]['id']) + "," + md5 + \
                 "," + str(fileMeta['mimeType']) + "," + deleted + "," + fullPath + "\n"
        self.file.write(string)
        self.closeFile()

    def addToDataBaseManual(self, id, parent, md5, mimeType, deleted, fullPath):
        self.openFile("a+")
        string = id + "," + parent + "," + md5 + "," + mimeType + "," + deleted + "," + fullPath + "\n"
        self.file.write(string)
        self.closeFile()

    def isInDataBase(self, fileID):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                self.closeFile()
                return True
        self.closeFile()
        return False

    def openFile(self, mode):
        self.file = open(DB_FILE, mode)

    def closeFile(self):
        self.file.close()

    def updateRecord(self, fileMeta, fullPath, deleted="false"):
        # remove it
        self.removeFromDataBase(fileMeta['id'])
        # re-add it with the new md5
        self.addToDataBase(fileMeta, fullPath, deleted)

    def getMd5(self, fileID):
        # find md5 in file form id
        # return it
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                return id1[2]
        self.closeFile()

    def isDeleted(self, fileID):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                print id1[4]
                if id1[4] is "true":
                    self.closeFile()
                    return True
        self.closeFile()
        return False

    def setDeleted(self, fileID):
        self.openFile("r")
        line = None
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                line = id1
        self.closeFile()
        if line is not None:
            self.removeFromDataBase(fileID)
            self.addToDataBaseManual(line[0], line[1], line[2], line[3], "true", line[5].strip("\n"))

    def getFilePath(self, fileID):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[0] == fileID:
                return id1[-1].strip("\n")
        self.closeFile()

    # Can be used to get parent folder id's
    def getIdFromPath(self, fullPath):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if id1[-1].strip("\n") == fullPath:
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
            if id1[-1].strip("\n") == path:
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
    print "GDrive client initializing..."
    GA = Authorization()
    GA.initializeDriveService()
    print "Authorisation complete."
    FM = FileManagement()
    print "File Manager initialized."
    print "Refreshing drive caches and local databases..."
    # Do initial sync to load caches
    FM.cloudSyncAll('root')
    FM.localSyncAll(SYNC_FOLDER)
    FM.dataBaseSync()
    print "Done!"
    print "Initialization complete!"
    print ""
    start = time.time()
    while 1:
        try:
            # start = time.time()
            # Run cloud sync on another thread and only sync every 5 mins or so
            currentTime = time.time()
            if(currentTime - start) > 10:
                # Reset the drive list after were done so we can get fresh data
                FM.currentDriveFileList = []
                sys.stdout.write("\r"+"[" + datetime.datetime.now().time().strftime('%H:%M:%S') + "]: "+" Syncing..."),
                syncStart = time.time()
                FM.cloudSyncAll('root')
                FM.localSyncAll(SYNC_FOLDER)
                start = currentTime
                sys.stdout.write("\r" + "[" + datetime.datetime.now().time().strftime('%H:%M:%S') + "]: " +
                                 "Sync Complete in {:.2f} seconds. {} new files downloaded. "
                                 "{} new files uploaded. {} files updated.".format(
                                 (time.time() - syncStart), FM.filesDownloaded, FM.filesUploaded, FM.filesOverwritten))
                sys.stdout.flush()
            FM.dataBaseSync()

            FM.filesDownloaded = 0
            FM.filesUploaded = 0
            FM.filesOverwritten = 0
            # time.sleep(5)
        except KeyboardInterrupt:
            break
        except Exception, e:
            print e
            break
        finally:
            FM.dataBase.closeFile()


if __name__ == "__main__":  # load settings like filepath etc, if its not there use add sys arguments to determine sync folder etc
    arguments = sys.argv
    if len(arguments) > 1:
        sync = arguments[1]
        print('Arguments given: ', sync)
        print('This argument will change the sync path')
    run()
    # GA = Authorization()
    # GA.initializeDriveService()
    # FM = FileManagement()
    # FM.localSyncAll(SYNC_FOLDER)
