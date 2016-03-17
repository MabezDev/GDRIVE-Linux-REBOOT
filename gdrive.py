import hashlib
import os
import sys
import time

import httplib2
import oauth2client
import apiclient
from oauth2client import client
from oauth2client import tools

#global variables

CREDENTIALS_FILE = "mycreds.txt"
APP_NAME = "GRIVE Client"
CLIENT_SECRET_FILE = "client_secrets.json"
SCOPES = ["https://www.googleapis.com/auth/drive"]

#INSTALL = "/home/Mabez/Computing/GDRIVE/" # These two need to change
#SYNC_FOLDER = "/home/Mabez/Documents/SYNC/"
SYNC_FOLDER = "C:/Users/Mabez/Documents/GDRIVE/files/"
INSTALL  = "C:/Users/Mabez/Documents/GDRIVE/"

RES_FOLDER = INSTALL+ "res/"
DB_HOME = RES_FOLDER+"db/"
DB_FILE = DB_HOME + "filedb.db"
CONFIG = RES_FOLDER + "config.ini"

class Authorization():
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
        elif(self.credentials.access_token_expired):
            print("Credentials are expired. Attempting to refresh...")
            try:
                self.credentials.refresh()
            except Exception:
                print("Refresh failed.")
        else:
            print("Found credentials in "+CREDENTIALS_FILE)
        return self.credentials
    def initializeDriveService(self):
        http = httplib2.Http()
        http = self.credentials.authorize(http)
        global DRIVE_SERVICE
        DRIVE_SERVICE = apiclient.discovery.build("drive", "v2", http=http)


class FileManagement():
    def __init__(self):
        #create sync_folder if it doesn't exist
        if(not self.folderExists(SYNC_FOLDER)):
            self.makeDirectory(SYNC_FOLDER)
        self.workingDirectory = SYNC_FOLDER
        self.currentDriveFolder = 'root'
        self.Downloaded = 0
        self.totalFiles = 0
        self.filesDownloaded = 0
        self.filesUploaded = 0
        self.filesOverwritten = 0
        # initialize database
        self.dataBase = DataBaseManager()
        global LOCAL_FILE_REMOVED
        LOCAL_FILE_REMOVED = []
        global LOCAL_FILE_ADDED
        LOCAL_FILE_ADDED = []
    def downloadAll(self):
        self.downloadAllFromFolder("root")

    def getFileList(self,folderId):
        return DRIVE_SERVICE.files().list(q="'{0}' in parents and trashed=false".format(folderId)).execute().get('items',[])
    def downloadAllFromFolder(self,folderId):
        file_list = self.getFileList(folderId)
        self.totalFiles += len(file_list)
        print(file_list)
        for doc in file_list:
            if("application/vnd.google-apps." in doc['mimeType']):
                if(not doc['mimeType']=="application/vnd.google-apps.folder"):
                    self.downloadGDriveFile(doc,self.workingDirectory)
                else:
                    path = str(self.workingDirectory+doc['title']+"/")
                    if(not self.folderExists(path)):
                        self.totalFiles -= 1
                        self.makeDirectory(path)
                        self.setWorkingDirectory(path)
                        self.downloadAllFromFolder(doc['id'])
            else:
                self.downloadFile(doc,self.workingDirectory,doc['mimeType'])
        self.setWorkingDirectory(SYNC_FOLDER)#return to root
    def cloudSyncAll(self,folderId):
        file_list = self.getFileList(folderId)
        for doc in file_list:
            if("application/vnd.google-apps." in doc['mimeType']):
                if(not doc['mimeType']=="application/vnd.google-apps.folder"):
                    pass
                    #not sure howto organize gdoc files as of yet
                    #only need add or remove stuff
                else:
                    path = str(self.workingDirectory+doc['title']+"/")
                    if(not self.folderExists(path)):
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
        for i in range((len(paths)-2)):
            self.prevPath += paths[i]+"/"
        if(not self.workingDirectory==SYNC_FOLDER):
            self.setWorkingDirectory(self.prevPath)

    def localSyncAll(self,folderId):
        file_list = self.getFileList(folderId)
        for doc in file_list:
            if("application/vnd.google-apps." in doc['mimeType']):
                if(not doc['mimeType']=="application/vnd.google-apps.folder"):
                    pass
                    #not sure howto organize gdoc files as of yet
                    #create folder on drive
                    #set working directory to this path
                else:
                    path = str(self.workingDirectory+doc['title']+"/")
                    if(not self.folderExists(path)):
                        self.makeDirectory(path)
                    self.totalFiles -= 1
                    self.setWorkingDirectory(path)
                    self.currentDriveFolder = doc['id']

                    self.checkFolders()

                    self.localSyncAll(doc['id'])
            else:
                self.localSync(doc)

        self.currentDriveFolder = 'root'
        paths = self.workingDirectory.split("/")
        self.prevPath = ""
        for i in range((len(paths)-2)):
            self.prevPath += paths[i]+"/"
        if(not self.workingDirectory==SYNC_FOLDER):
            self.setWorkingDirectory(self.prevPath)

    def createFolderInDrive(self,title):
        ##redo
        folder = DRIVE_SERVICE.CreateFile({'title':'{0}'.format(title),'mimeType':'application/vnd.google-apps.folder',"parents": [{"kind": "drive#fileLink","id": self.currentDriveFolder}]})
        folder.Upload()

    def setWorkingDirectory(self,path):
        self.workingDirectory = path

    def downloadFile(self,fileMeta,folder,mimeType):
        fullPath = folder+fileMeta['title']
        if(not self.folderExists(folder)):
            self.makeDirectory(folder)
        #print("Downloading {0} with id {1}".format(fileMeta['title'],fileMeta['id']))
        print("Downloading From Drive: ",fileMeta['title'])
        fileDownload = fileMeta.get('downloadUrl')
        if fileDownload:
            resp, content = DRIVE_SERVICE._http.request(fileDownload)
            if resp.status == 200:
                print('Status: %s' % resp)
            f = open(fullPath, "w") ## write content
            f.write(content)
            f.close()
        else:
            print("Error downloading file. No content detected.")
        #add to data base
        self.dataBase.addToDataBase(fileMeta['id'],fileMeta['md5Checksum'],fullPath)
        #increase tally
        self.Downloaded += 1

    def downloadGDriveFile(self,fileMeta,folder):
        fullPath = folder+fileMeta['title']+".desktop"
        shortcutImg = RES_FOLDER + "doc.png"
        end = "\n"
        if(not self.folderExists(folder)):
            self.makeDirectory(folder)
        if(not self.fileExists(fullPath)):
            f = open(fullPath,"w")
            f.write("[Desktop Entry]"+end)
            f.write("Encoding=UTF-8"+end)
            f.write("Name="+fileMeta['title']+end)
            f.write("Type=Link"+end)
            f.write("URL="+fileMeta['alternateLink']+end)
            f.write("Icon="+shortcutImg+end)
            f.close()
            self.Downloaded += 1

    def folderExists(self,folder):
        return os.path.isdir(folder)
    def fileExists(self,fileLocation):
        return os.path.isfile(fileLocation)
    def makeDirectory(self,path):
        os.mkdir(path)

    def getLocalMd5(self,fullPath):#works perfectly returns the same md5s as googles
        if(self.fileExists(fullPath)):
            return hashlib.md5(open(fullPath,'rb').read()).hexdigest()
        else:
            print("No File to hash, path: ",fullPath)
            dirs = fullPath.split("/")
            self.removeFromDrive('root',dirs[(len(dirs))-1])

    def cloudSync(self,fileMeta):#not checking folder
        #check if cloud has new file --> initiate download
        #if cloudMd5!=dbmd5 && dbmd5==localmd5 cloud has changed --> initiate overwrite --> update db with new md5 for specific id
        fileID = fileMeta['id']
        title = fileMeta['title']

        if(self.fileExists(self.workingDirectory+title)):
            if(self.dataBase.isInDataBase(fileID)):
                storedMd5 = self.dataBase.getMd5(fileID)
                cloudMd5 = fileMeta['md5Checksum']
                local = self.dataBase.getFilePath(fileID)
                if(cloudMd5!=storedMd5 and self.getLocalMd5(local)==storedMd5):
                    #print("Overwriting Local File :",doc['title'])#overwriting from cloud
                    self.downloadFile(fileMeta,self.workingDirectory,fileMeta['mimeType'])
                    self.dataBase.updateRecord(fileID,cloudMd5,local)
                    self.filesOverwritten +=1
        else:
            #new file --> download it
            if("application/vnd.google-apps." in fileMeta['mimeType']):
                if(not fileMeta['mimeType']=="application/vnd.google-apps.folder"):
                    pass
                        #self.downloadGDriveFile(doc,self.workingDirectory)
                        #not sure what to do with GDoc files yet
            else:
                self.downloadFile(fileMeta,self.workingDirectory,fileMeta['mimeType'])
                self.filesDownloaded+=1

    def checkFolders(self):#check folders not working properly
        folders = os.walk(self.workingDirectory)
        for folder in folders:
            print("Folder is: ",folder[0])
            if(folder[0]==SYNC_FOLDER):
                continue
            if(os.path.isdir(folder[0])):
                #print("Checking if '{0}' is in drive.".format(folder[0]))
                dirs = folder[0].split("/")
                print("Dirs: ",dirs)
                index = 1
                fileName = dirs[(len(dirs)-index)]
                while fileName=='':
                    fileName = dirs[len(dirs)-index]
                    index+=1
                print(fileName)
                if(not self.isInDrive(self.currentDriveFolder,fileName)):
                        print("Creating folder in drive called: ",fileName)
                        #self.createFolderInDrive(fileName)
    def localSync(self,fileMeta):
            fileID = fileMeta['id']
            fileCheckSum = fileMeta['md5Checksum']
            title = fileMeta['title']
            #if local!= db && db==cloud --> local has changed --> iniate upload(overwrite) to drive --> update db with new md5 for specific id
            if(self.dataBase.isInDataBase(fileID)):
                path = self.dataBase.getFilePath(fileID)
                localmd5 = self.getLocalMd5(path)
                dbmd5 = self.dataBase.getMd5(fileID)
                #print("DBMD5: {0} LOCALMD5: {1} CLOUDMD5: {2}".format(dbmd5,localmd5,fileCheckSum))
                if((localmd5!=dbmd5) and (str(fileCheckSum)==dbmd5)):
                    #overwrite online
                    print('File md5 has changed at : ',path)
                    if(self.fileExists(path)):
                        body = {
                            "title":title,
                            "mimeType":str(fileMeta['mimeType'])
                        }
                        ##Error uploading need to fix tommorrow
                        body['parents'] = [{str(id):self.currentDriveFolder}]#str is very import else it throws a json key error
                        media_body = apiclient.http.MediaFileUpload(path,fileMeta['mimeType'],resumable=True)
                        DRIVE_SERVICE.files().insert(body=body,media_body=media_body).execute()
                        self.dataBase.updateRecord(fileID,localmd5,path)
                        self.filesOverwritten+=1
                    else:
                        print(title," doesnt exists!")
                        self.dataBase.removeFromDataBase(fileID)




            #check if local has new file --> initiate upload
            files = os.listdir(self.workingDirectory)

            for doc in files:
                filePath = self.workingDirectory+doc
                if(self.dataBase.getIdFromPath(filePath)==None):
                    self.uploadFile(doc,filePath)#upload new file







            ''' #THIS MAKES SYNC VERY SLOW
            #when a file has been delete locally it needs to be removed from the database
            file_list = DRIVE_SERVICE.ListFile({'q':"'{0}' in parents and trashed=false".format(self.currentDriveFolder)}).GetList()
            for doc in file_list:
                if(not doc['mimeType']=="application/vnd.google-apps.folder"):
                    if(not doc['title'] in files):
                        #if its not in local files then remove the id from db and redownload
                        if(self.dataBase.isInDataBase(doc['id'])):
                            print('In drive but not local, removing {0} from database.'.format(doc['title']))
                            self.dataBase.removeFromDataBase(doc['id'])
            '''


class DataBaseManager():
    def __init__(self):
        if(not os.path.exists(DB_HOME)):
            os.mkdir(DB_HOME)
        if(not os.path.isfile(DB_FILE)):
            f = open(DB_FILE,"w")
            f.close()
        self.file = open(DB_FILE,"r")
        self.closeFile()
    def addToDataBase(self,fileID,md5,fullPath):
        self.openFile("a+")
        string = str(fileID)+","+str(md5)+","+fullPath+"\n"
        self.file.write(string)
        self.closeFile()
    def isInDataBase(self,fileID):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if(id1[0]==fileID):
                return True
        self.closeFile()
        return False
    def openFile(self,mode):
        self.file = open(DB_FILE,mode)
    def closeFile(self):
        self.file.close()
    def updateRecord(self,fileID,newMd5,fullPath):
        #remove it
        self.removeFromDataBase(fileID)
        #re-add it with the new md5
        self.addToDataBase(fileID,newMd5,fullPath)
    def getMd5(self,fileID):
        # find md5 in file form id
        # return it
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if(id1[0]==fileID):
                return id1[1]
        self.closeFile()
    def getFilePath(self,fileID):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if(id1[0]==fileID):
                return id1[2].strip("\n")
        self.closeFile()
    def getIdFromPath(self,fullPath):
        self.openFile("r")
        for line in self.file:
            id1 = line.split(",")
            if(id1[2].strip("\n")==fullPath):
                return id1[0]
        self.closeFile()

    def removeFromDataBase(self,fileID):
        self.openFile("r+")
        lines = self.file.readlines()
        self.file.seek(0)
        for line in lines:
            if not fileID in line:# if id is NOT in line then write it
                self.file.write(line)
        self.file.truncate() #remove the extras
        self.closeFile()


    #database has basic functionality

def run():
    GA = Authorization()
    GA.initializeDriveService()
    FM = FileManagement()
    while 1:
        try:
            FM.cloudSyncAll('root')
            FM.localSyncAll('root')
            print('Sync Complete. {0} new files downloaded. {1} new files uploaded. {2} files updated.'.format(FM.filesDownloaded,FM.filesUploaded,FM.filesOverwritten))
            FM.filesDownloaded = 0
            FM.filesUploaded = 0
            FM.filesOverwritten = 0
            time.sleep(5)
        except KeyboardInterrupt:
            break
        finally:
            FM.dataBase.closeFile()

if __name__ == "__main__":#load settings like filepath etc, if its not there use add sys arguments to determine sync folder etc
    arguments = sys.argv
    print(arguments)
    if(len(arguments)>1):
        sync = arguments[1]
        print('Arguments given: ',sync)
        print('This argument will change the sync path')
    run()
    #GA = Authorization()
    #GA.initializeDriveService()
    #FM = FileManagement()
    #FM.downloadAll()
