import socketserver
import hashlib # SHA-1
import codecs # BASE64
from pymongo import MongoClient
mongoClient = MongoClient("db", 27017)
database = mongoClient["database"]
dbChats = database["dbChats"] 

class MyTCPHandler(socketserver.BaseRequestHandler):
    socketClients = []
    socketChats = []

    # Parses web frame
    def parseWebframe(self,encode):
        binaryWebframe = []
        for byte in encode:
            val = bin(byte)[2:]
            while(8 - len(val) != 0):
                val = '0' + val
            binaryWebframe.append(val)

    
        # Payload len parsing
        maskBit = binaryWebframe[1][0]
        if(int(maskBit) == 1): #Recieving from client
            payloadStr = binaryWebframe[1][1:]
            payloadlen= int(payloadStr,2)
            if(payloadlen >= 126):
                mask = binaryWebframe[4:8]
                maskedPayload = binaryWebframe[8:]
                payload = []
                for index, byte in enumerate(maskedPayload):
                    payload.append(int(self.xor(byte, mask[index % 4]),2))
                
                payloadBytes = bytearray(payload)
                payloadBytes = self.removeHTML(payloadBytes)
                binaryLength = bin(len(payloadBytes))[2:]
                while(16 - len(binaryLength) != 0):
                    binaryLength = '0' + binaryLength
                # After unmasking, send from server to client
                sendFrame = [129]
                sendFrame += [126]
                sendFrame+= [int(binaryLength[:8],2)]
                sendFrame += [int(binaryLength[8:],2)]
                self.socketChats.append(bytearray(sendFrame) + payloadBytes)
                chatVal = payloadBytes.decode()
                dataVal = {"chat": chatVal}
                x = dbChats.insert_one(dataVal)
                for client in self.socketClients:
                    client.sendall(bytearray(sendFrame) + payloadBytes)
            else:
                mask = binaryWebframe[2:6]
                maskedPayload = binaryWebframe[6:]
                payload = []
                for index, byte in enumerate(maskedPayload):
                    payload.append(int(self.xor(byte, mask[index % 4]),2))

                payloadBytes = bytearray(payload)
                payloadBytes = self.removeHTML(payloadBytes)
                # After unmasking, send from server to client
                sendFrame = [129]
                sendFrame += [len(payloadBytes)]
                self.socketChats.append(bytearray(sendFrame) + payloadBytes)
                chatVal = payloadBytes.decode()
                dataVal = {"chat": chatVal}
                x = dbChats.insert_one(dataVal)
                for client in self.socketClients:
                    client.sendall(bytearray(sendFrame) + payloadBytes)

        else:   #Sending to client
            print("Send data to client")
    
    # Returns xor of two string binary values and returns as string
    def xor(self,value1,value2):
        retVal = ''
        for index,char  in enumerate(value1):
            int1 = int(char)
            int2 = int(value2[index])
            if int1 == 0 and int2 == 0:
                retVal = retVal + '0'
            elif int1 == 0 and int2 == 1:
                retVal = retVal + '1'
            elif int1 == 1 and int2 == 0:
                retVal = retVal + '1'
            elif int1 == 1 and int2 == 1:
                retVal = retVal + '0'
        return(retVal)


    # Does the proper hashing for web socket
    def webSocketHashing(self, key):
        retVal = key
        # Add GUID to key
        retVal = retVal + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'.encode()
        # Compute the SHA-1 Hash
        retVal = hashlib.sha1(retVal).hexdigest()
        # Compute BASE-64 encoding
        retVal = codecs.decode(retVal, 'hex')
        retVal = codecs.encode(retVal, 'base64')
        retVal = retVal.replace('\n'.encode(), ''.encode())
        return retVal

    # Parses and finds the web socket key
    def handleWebSocket(self,recArr):
        webSocketKey = ''
        for val in recArr:
            if 'Sec-WebSocket-Key:'.encode() in val:
                webSocketKey = val.split('Sec-WebSocket-Key:'.encode())[1]
        hashedKey = self.webSocketHashing(webSocketKey.strip())
        self.request.sendall(("HTTP/1.1 101 Switching Protocols\r\nConnection: Upgrade" + "\r\nUpgrade: websocket\r\nSec-WebSocket-Accept: ").encode() + hashedKey + "\r\n\r\n".encode())
        
        dataChats = database.dbChats.find()
        for chat in dataChats:
            payloadBytes = chat.get('chat').encode()
            payloadArr = bytearray(payloadBytes)

            if(len(payloadArr) >= 126):
                binaryLength = bin(len(payloadBytes))[2:]
                while(16 - len(binaryLength) != 0):
                    binaryLength = '0' + binaryLength
                # After unmasking, send from server to client
                sendFrame = [129]
                sendFrame += [126]
                sendFrame+= [int(binaryLength[:8],2)]
                sendFrame += [int(binaryLength[8:],2)]
                self.request.sendall(bytearray(sendFrame) + payloadArr)
            else:
                sendFrame = [129]
                sendFrame += [len(payloadBytes)]
                self.request.sendall(bytearray(sendFrame) + payloadArr)
                    

    #Creates custom html for images name
    def customTemplate(self, images, names):
        templateFile = open('customTemplate.html', 'r')
        template= templateFile.read()
        nameReplacement = ""
        imageReplacement=""
        for name in names:
            nameReplacement += "<h1>"+name+"</h1>"
        for image in images:
            imageReplacement += "<img src=image/"+image+".jpg />"
        custom = template.replace("{{title}}", "Welcome, " + nameReplacement)
        custom = custom.replace("{{images}}", imageReplacement)
        templateFile.close()
        self.request.sendall(("HTTP/1.1 200 OK\r\nContent-Length: " + str(len(custom))+ "\r\nContent-Type: text/html\r\nX-Content-Type-Options: nosniff\r\n\r\n" + custom).encode())

    #Dividies up the queries
    def querySearch(self, query):
        imageArr = []
        nameArr = []
        splitQueries = query.split('&')
        for q in splitQueries:
            qSeperated = q.split('=') #Seperates name[0] from elements [1]
            if qSeperated[0] == 'images':
                imageArr = qSeperated[1].split('+')
            elif qSeperated[0] == 'name':
                nameArr = qSeperated[1].split('+')
        self.customTemplate(imageArr, nameArr)

    #Sends a singular image
    def hostImage(self, imageName):
        imageFile = open('./images/' + imageName, "rb")
        imageRead = imageFile.read()
        self.request.sendall(("HTTP/1.1 200 OK \r\nContent-Length: " + str(len(imageRead)) + "\r\nContent-Type: image/jpeg\r\nX-Content-Type-Options: nosniff\r\n\r\n").encode()+ imageRead)
        imageFile.close()

    # Escapes HTML
    def removeHTML(self, bArray):
        retVal = bArray.replace("&".encode(), "&amp;".encode())
        retVal = retVal.replace("<".encode(), "&lt;".encode())
        retVal = retVal.replace(">".encode(), "&gt;".encode())
        return retVal

    # Adds the form inputs to html
    def addForm(self, name,comment):
        if(len(name) > 0 or len(comment) > 2):
            chats.append([name,comment])
        self.request.sendall("HTTP/1.1 301 Moved \r\nLocation: /".encode())

    def addImage(self, upload, name, filename):
        # self.request.sendall("HTTP/1.1 301 Moved \r\nLocation: /".encode())
        name = self.removeHTML(name)
        filename = self.removeHTML(filename)
        filename = filename.replace("\"".encode(),"".encode())
        f = open(filename.decode(), "wb")
        f.write(upload)
        f.close()
        imageCaptions.append([filename,name])
        self.request.sendall("HTTP/1.1 301 Moved \r\nLocation: /".encode())
        # self.request.sendall(("HTTP/1.1 200 OK \r\nContent-Length: " + str(len(upload)) + "\r\nContent-Type: image/jpeg\r\nX-Content-Type-Options: nosniff\r\n\r\n").encode()+ upload)

    def handlePostRequest(self, encode, pathName):

        bArray = bytearray()
        recArr = encode.split('\r\n\r\n'.encode(),1)
        if(len(recArr) > 1):
            recArr = recArr[1]
            bArray += recArr

        # Finding Content Length & Boundary
        ContentLength = -1
        BoundaryName = ''
        recArr = encode.split('\r\n'.encode())
        for entry in recArr:
            # Finding Content Length
            if "Content-Length:".encode() in entry:
                for elem in entry.decode().split():
                    if elem.isdigit():
                        ContentLength = int(elem)
            # Finding Content Boundary
            if "Content-Type:".encode() in entry:
                cT =entry.split(';'.encode())
                for x in cT:
                    if 'boundary'.encode() in x:
                        startIndex = x.index('boundary='.encode())
                        startIndex = startIndex + len('boundary='.encode())
                        BoundaryName=x[startIndex:]
        # Recieving data from server until content length reached
        while(ContentLength > len(bArray)):
            recieved_data = self.request.recv(1024)
            bArray += recieved_data

        print (bArray)
        # Splitting up recieved data by boundaries and putting it into the parts array
        parts =[]
        imageName = []
        for part in bArray.split('--'.encode() + BoundaryName):
            elem = []
            takeNext = False
            for subPart in part.split('\r\n\r\n'.encode()):
                if 'Content-Disposition:'.encode() in subPart:
                    elem.append(subPart)
                    takeNext = True
                elif takeNext:
                    elem.append(subPart)
                    parts.append(elem)

        # Putting form data onto the page
        if pathName == "/comment".encode():

            name = []
            comment = []
            for part in parts:
                if '"name"'.encode() in part[0]:
                    name = part[1].split('\r\n'.encode())
                elif '"comment"'.encode() in part[0]:
                    comment = part[1].split('\r\n'.encode())
            if(len(comment) > 0):
                comment = self.removeHTML(comment[0])
            if(len(name) > 0):
                name = self.removeHTML(name[0])
            self.addForm(name, comment)
        elif pathName == "/image-upload".encode():
            upload = []
            name = []
            filename = []
            for part in parts:
                if "filename".encode() in part[0]:
                    spl = part[0].split("filename=".encode())
                    filename= spl[1].split('\r\n'.encode())[0]
                if '"upload"'.encode() in part[0]:
                    # upload = part[1].split('\r\n'.encode())
                    # print(len(part[1]))
                    # print(len(upload[0]))
                    # # print(len(upload[1]))
                    # print(part)
                    endIndex = len(part[1]) - len('\r\n'.encode())
                    upload = part[1][:endIndex]
                elif '"name"'.encode() in part[0]:
                    name = part[1].split('\r\n'.encode())
            # if(len(upload) > 0):
            #     upload = self.removeHTML(upload[0])
            # if(len(comment) > 0):
            #     comment = self.removeHTML(comment[0])
            # print(ContentLength)
            
            self.addImage(upload, name[0], filename)
        # self.request.sendall(("HTTP/1.1 200 OK\r\nContent-Length: " + str(len(commentSubmission)) + "\r\nContent-Type: text/plain\r\n\r\n").encode() + commentSubmission)

    
    def handleGetRequest(self, recArrArr):

            #     functionsFile.close()
        ### Custom site ###
            if recArrArr[1] == "/":
                indexFile = open("./customFrontend/index.html", "r")
                indexRead = indexFile.read()
                chatReplacement = ""
                for chat in chats:
                    chatReplacement += "<p>"+chat[0].decode()+ ":    " + chat[1].decode()+"</p>"
                for image in imageCaptions:
                    chatReplacement+= "<img src=uploaded/" + image[0].decode() + "/>"
                    chatReplacement+= "<p>"+ image[1].decode() + "</p>" 
                custom = indexRead.replace("</div>", chatReplacement + "</div>")
                self.request.sendall(("HTTP/1.1 200 OK\r\nContent-Length: " + str(len(custom))+"\r\nContent-Type: text/html\r\nX-Content-Type-Options: nosniff\r\n\r\n" + custom).encode())
                indexFile.close()

            ### Custom site ###
            elif recArrArr[1] == "/style.css":
                styleFile = open("./customFrontend/style.css", "r")
                styleRead = styleFile.read()
                self.request.sendall(("HTTP/1.1 200 OK \r\nContent-Length: " + str(len(styleRead))+"\r\nContent-Type: text/css\r\nX-Content_Type-Options: nosniff\r\n\r\n" + styleRead).encode())
                styleFile.close()

            ### Custom site ###
            elif recArrArr[1] == "/functions.js":
                functionsFile = open("./customFrontend/functions.js", "r")
                functionsRead = functionsFile.read()
                self.request.sendall(("HTTP/1.1 200 OK \r\nContent-Length: " + str(len(functionsRead)) +"\r\nContent-Type: text/javascript\r\nX-Content-Type-Options: nosniff\r\n\r\n" + functionsRead).encode())
                functionsFile.close()

            elif recArrArr[1] == "/utf.txt":
                utfFile = open("utf.txt", "r")
                utfRead = utfFile.read()
                utfEncode = utfRead.encode("utf-8")
                self.request.sendall(("HTTP/1.1 200 OK\r\nContent-Length: " + str(len(utfEncode)) + "\r\nContent-Type: text/html; charset=utf-8\r\nX-Content-Type-Options: nosniff\r\n\r\n" + utfRead).encode())
                utfFile.close()

            elif recArrArr[1] == "/image/cat.jpg":
                self.hostImage("cat.jpg")

            elif recArrArr[1] == "/image/dog.jpg":
                self.hostImage("dog.jpg")

            elif recArrArr[1] == "/image/eagle.jpg":
                self.hostImage("eagle.jpg")

            elif recArrArr[1] == "/image/elephant.jpg":
                self.hostImage("elephant.jpg")

            elif recArrArr[1] == "/image/flamingo.jpg" or recArrArr[1] == "/images/flamingo.jpg":
                self.hostImage("flamingo.jpg")

            elif recArrArr[1] == "/image/kanye.jpg" or recArrArr[1] == "/images/kanye.jpg":
                self.hostImage("kanye.jpg")

            elif recArrArr[1] == "/image/kitten.jpg":
                self.hostImage("kitten.jpg")
            
            elif recArrArr[1] == "/image/parrot.jpg":
                self.hostImage("parrot.jpg")

            elif recArrArr[1] == "/image/rabbit.jpg":
                self.hostImage("rabbit.jpg")

            elif "/images" in recArrArr[1]:
                if "?" in str(recArrArr[1]):
                    query = recArrArr[1].split('?')[1]
                    self.querySearch(query)

            elif "/uploaded/" in recArrArr[1]:
                imageReq = recArrArr[1].split('uploaded/')[1]
                for image in imageCaptions:
                    print(imageReq)
                    print(image[0])
                    if(image[0].decode() + "/" == imageReq):
                        imageFile = open('./' + image[0].decode(), "rb")
                        imageRead = imageFile.read()
                        self.request.sendall(("HTTP/1.1 200 OK \r\nContent-Length: " + str(len(imageRead)) + "\r\nContent-Type: image/jpeg\r\nX-Content-Type-Options: nosniff\r\n\r\n").encode()+ imageRead)
                        imageFile.close()
                        return
                else:
                    self.request.sendall("HTTP/1.1 404 Not Found\r\nContent-Length: 17 Content-Type: text/plain\r\n\r\nPage not found :(".encode())

            

            else:
                self.request.sendall("HTTP/1.1 404 Not Found\r\nContent-Length: 17 Content-Type: text/plain\r\n\r\nPage not found :(".encode())

    #Handles requests
    def handleRequest(self, encode, clientID):
        recArr = encode.split('\r\n'.encode())
        recArrArr = recArr[0].split(" ".encode())
        print(encode)
        if len(recArrArr) > 1: 

            if recArrArr[0] == 'POST'.encode():
                self.handlePostRequest(encode, recArrArr[1])
            elif recArrArr[1] == '/websocket'.encode():
                self.socketClients.append(self.request)
                self.handleWebSocket(recArr)
            elif recArrArr[0] == 'GET'.encode():
                recArr = encode.decode().split('\r\n')
                recArrArr = recArr[0].split(" ")
                self.handleGetRequest(recArrArr)
        # Else for websocket message
        else:
            self.parseWebframe(encode)

    def handle(self):
        try:
            while(True):
                recieved_data = self.request.recv(1024)
                print(self.client_address[0] + " is sending data:")
                clientID = self.client_address[0] + ":" + str(self.client_address[1])
                self.handleRequest(recieved_data, clientID)
        except:
            pass




if __name__ == "__main__":
    host = "0.0.0.0"
    port = 8000
    print("Server is running on port " + str(port))

    global chats
    chats  = []
    global imageCaptions
    imageCaptions = []

    server = socketserver.ThreadingTCPServer((host, port), MyTCPHandler)
    server.serve_forever()