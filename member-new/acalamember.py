from kubernetes import config
import kubernetes.client
import requests
import time
import socket
import gzip
import shutil
import logging
from aiohttp import ClientSession
import asyncio
import numpy as np


timeout_seconds = 30
maindict = {}
averagemaindict = {}
cvmaindict = {}
helplist = []
checklist = []
lastmaindict = {}


logging.basicConfig(level=logging.INFO)

def timewriter(text):
    f = open("exectime", 'a')
    f.write(text)
    f.write("\n")
    f.close

def getControllerMasterIP():
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    master_ip = ""

    try:
        nodes = api_instance.list_node(
            pretty=True, _request_timeout=timeout_seconds)
        nodes = [node for node in nodes.items if
                'node-role.kubernetes.io/master' in node.metadata.labels]
        addresses = nodes[0].status.addresses
        master_ip = [i.address for i in addresses if i.type == "InternalIP"][0]
    except:
        print("Connection timeout after " +
            str(timeout_seconds) + " seconds to host cluster")

    return master_ip

def parseforsetkeys(textline):
    parseddata = textline.split("{")
    smalldata = parseddata[0].split("_")
    return set(smalldata)

def parseforsethelp(textline):
    parseddata = textline.split(" ")
    smalldata = parseddata[2].split("_")
    return set(smalldata)

def parsefortstrkey(textline):
    parsedata = textline.split("{")
    if "{" in textline:
        return str(parsedata[0]), str(parsedata[1])
    else:
        return str(parsedata[0])

def parseforstrhelp(textline):
    origdata = textline.strip('\n')
    parseddata = origdata.split(" ")
    return str(parseddata[2])

def parseforstrhelpANDtype(textline):
    origdata = textline.strip('\n')
    parseddata = origdata.split(" ")
    return str(parseddata[3]), str(parseddata[2])

def parsevalue(textline):
    origdata = textline.strip('\n')
    if "}" in origdata:
        firstparse = origdata.split("}")
        parseddata = firstparse[1].split(" ")
    else:
        parseddata = origdata.split(" ")

    return float(parseddata[1])

def parsename(textline):
    origdata = textline.strip('\n')
    if "}" in origdata:
        firstparse = origdata.split("}")
        parseddata = firstparse[0] + "}"
    else:
        firstparse = origdata.split(" ")
        parseddata = firstparse[0]

    return str(parseddata)

def gettargets(prom_host):
    start = time.process_time()
    prom_port = 30090
    prom_url = "http://" + str(prom_host) + ":" + \
                            str(prom_port) + "/api/v1/targets"
    prom_header = {'Accept-Encoding': 'gzip'}
    r = requests.get(url=prom_url,headers=prom_header)
    data = r.json()
    nomaster=str(prom_host) +":9100"
    scrapeurl = []
    for item in data["data"]["activeTargets"]:
        if item["labels"]["job"] == "node-exporter":
            if item["labels"]["instance"] != nomaster:
                scrapeurl.append(item["scrapeUrl"])
    end = time.process_time()
    timewriter("gettargets" + " " + str(end-start))
    return scrapeurl

def getmetrics(url):
    start = time.process_time()
    prom_url = url
    session = requests.Session()
    prom_header = {'Accept-Encoding': 'gzip'}
    r = session.get(url=prom_url, headers=prom_header)
    fname = "before"
    f = open(fname, 'w')
    f.write(r.text)
    f.close
    end = time.process_time()
    timewriter("getmetrics" + " " + str(end-start))

async def fetch(link, session):
    try:
        async with session.get(link) as response:
            html_body = await response.text()
            mergesametime(html_body)
    except:
        logging.warning("Get metrics failed")

async def asyncgetmetrics(links):
    async with ClientSession() as session:
        tasks = [asyncio.create_task(fetch(link, session)) for link in links]  # 建立任務清單
        await asyncio.gather(*tasks)

def mergebyline(line):
    global maindict
    global checklist
    tempdict = {}
    counterformetrics = 1
    helplistappend = helplist.append
    checklistappend = checklist.append
    tempdict=maindict.copy()
    if line[0] == "#":
        if counterformetrics % 2 == 0:
            if line not in helplist:
                helplistappend(line)
                checklistappend(parseforstrhelp(line))
        counterformetrics += 1
    else:
        value=parsevalue(line)
        metricsname=parsename(line)
        checksame=0
        for k in tempdict.items():
            if metricsname==k:
                checksame=1
                maindict[k].append(value)
        if checksame==0:
            maindict.setdefault(metricsname,[]).append(value)

def mergesametime(html_body):
    global maindict
    global checklist
    counterformetrics = 1
    valuelist = []
    metricsname = []
    tempdict = {}
    helplistappend = helplist.append
    checklistappend = checklist.append
    valuelistappend = valuelist.append
    metricsnameappend = metricsname.append
    
    if not maindict:
        number=0
    else:
        number=1

    for line in html_body.splitlines():
        if line[0] == "#":
            if counterformetrics % 2 == 0:
                if line not in helplist:
                    helplistappend(line)
                    checklistappend(parseforstrhelp(line))
            counterformetrics += 1
        else:
            if number==0:
                maindict.setdefault(parsename(line),[]).append(parsevalue(line))
            else:
                valuelistappend(parsevalue(line))
                metricsnameappend(parsename(line))

    if number!=0:
        tempdict = dict(zip(metricsname, valuelist))
        for k, value in tempdict.items():
            if k in maindict.keys():
                maindict[k].append(value)
            else:
                maindict.setdefault(k,[]).append(value)

def merge(path,counter):
    start = time.process_time()
    f = open(path, 'r')
    global maindict
    global timesdict
    global checklist
    counterformetrics = 1
    valuelist = []
    metricsname = []
    tempdict = {}
    helplistappend = helplist.append
    checklistappend = checklist.append
    valuelistappend = valuelist.append
    metricsnameappend = metricsname.append
    #tempdict=maindict.copy()
    for line in f.readlines():
        if line[0] == "#":
            if counterformetrics % 2 == 0:
                if line not in helplist:
                    helplistappend(line)
                    checklistappend(parseforstrhelp(line))
            counterformetrics += 1
        else:
            if counter==0:
                maindict.setdefault(parsename(line),[]).append(parsevalue(line))
            else:
                valuelistappend(parsevalue(line))
                metricsnameappend(parsename(line))
    
    if counter!=0:
        tempdict = dict(zip(metricsname, valuelist))
        for k, value in tempdict.items():
            if k in maindict.keys():
                maindict[k].append(value)
            else:
                maindict.setdefault(k,[]).append(value)
        #maindict = dict(zip(metricsname, valuelist))
    
            #tempdict = dict(zip(metricsname, valuelist))
            # for k in metricsname:
            #     if k in maindict.keys():
            #         maindict[k].append(value)
            # for k,value in tempdict.items():

                    #maindict.setdefault(k,[]).append(value)


            # value=parsevalue(line)
            # metricsname=parsename(line)
            # checksame=0
            # if counter==0:
            #     maindict.setdefault(metricsname,[]).append(value)
            #     #print(maindict)
            # else:
            #     for k in tempdict.items():
            #         if metricsname==k:
            #             checksame=1
            #             maindict[k].append(value)
            #             break
            #     if checksame==0:
            #         maindict.setdefault(metricsname,[]).append(value)
    # f.close()
    end = time.process_time()
    timewriter("merge" + " " + str(end-start))

def calcavg():
    start = time.process_time()
    global averagemaindict
    global cvmaindict
    for k in maindict.keys():
        # averagemaindict[k]=round(np.mean(maindict[k]),5)
        # cvmaindict[k]=round((np.std(maindict[k])/averagemaindict[k]),5)
        averagemaindict[k]=np.mean(maindict[k])
        cvmaindict[k]=np.std(maindict[k])/averagemaindict[k]
        if np.isnan(cvmaindict[k]):
            cvmaindict[k]=0
    end = time.process_time()
    timewriter("calcavg" + " " + str(end-start))

def rebuildfile(lastvaluefunction):
    start = time.process_time()
    global lastmaindict
    global averagemaindict
    global cvmaindict
    labeldict={}
    fname = "after"
    f = open(fname, 'w')
    tempmaindict = maindict.copy()
    mappingdict={}
    listforremove = []
    listforremoveappend = listforremove.append

    for k in maindict.keys():
        if "{" in k:
            mappingdict[k],labeldict[k]=parsefortstrkey(k)
        else: 
            mappingdict[k]=parsefortstrkey(k)

    for line in helplist:
        strtype, strhelp = parseforstrhelpANDtype(line)
        flag=1
        for k in tempmaindict.keys():
            if strhelp == mappingdict[k]:
                if lastvaluefunction:
                    if lastmaindict:
                        if tempmaindict[k] != lastmaindict[k]:
                            if strtype == "counter":
                                data = str(k) + " " + str(int(averagemaindict[k]))
                                if "{" in k:
                                    datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
                                else:
                                    datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
                                listforremoveappend(k)
                            else:
                                data = str(k) + " " + str(averagemaindict[k])
                                if "{" in k:
                                    datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
                                else:
                                    datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
                                listforremoveappend(k)
                            if flag:
                                f.write(line)
                                f.write("\n")
                                flag=0
                            f.write(data)
                            f.write("\n")
                            f.write(datacv)
                            f.write("\n")
                    else:
                        if strtype == "counter":
                            data = str(k) + " " + str(int(averagemaindict[k]))
                            if "{" in k:
                                datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
                            else:
                                datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
                            listforremoveappend(k)
                        else:
                            data = str(k) + " " + str(averagemaindict[k])
                            if "{" in k:
                                datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
                            else:
                                datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
                            listforremoveappend(k)
                        if flag:
                            f.write(line)
                            f.write("\n")
                            flag=0
                        f.write(data)
                        f.write("\n")
                        f.write(datacv)
                        f.write("\n")
                else:
                    if strtype == "counter":
                        data = str(k) + " " + str(int(averagemaindict[k]))
                        if "{" in k:
                            datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
                        else:
                            datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
                        listforremoveappend(k)
                    else:
                        data = str(k) + " " + str(averagemaindict[k])
                        if "{" in k:
                            datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
                        else:
                            datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
                        listforremoveappend(k)
                    if flag:
                        f.write(line)
                        f.write("\n")
                        flag=0
                    f.write(data)
                    f.write("\n")
                    f.write(datacv)
                    f.write("\n")
            # elif strtype == "summary" or strtype=="histogram":
            #     if strtype=="histogram":
            #         if flag:
            #             f.write(line)
            #             f.write("\n")
            #             flag=0
            #     if lastvaluefunction:
            #         sethelp = parseforsethelp(line)
            #         if parseforsetkeys(k).issuperset(sethelp):
            #             if mappingdict[k] not in checklist:
            #                 if lastmaindict:
            #                     if tempmaindict[k] != lastmaindict[k]:
            #                         if strtype == "counter":
            #                             data = str(k) + " " + str(int(averagemaindict[k]))
            #                             if "{" in k:
            #                                 datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
            #                             else:
            #                                 datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
            #                             listforremoveappend(k)
            #                         else:
            #                             data = str(k) + " " + str(averagemaindict[k])
            #                             if "{" in k:
            #                                 datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
            #                             else:
            #                                 datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
            #                             listforremoveappend(k)
            #                         f.write(data)
            #                         f.write("\n")
            #                         f.write(datacv)
            #                         f.write("\n")
            #                 else:
            #                     if strtype == "counter":
            #                         data = str(k) + " " + str(int(averagemaindict[k]))
            #                         if "{" in k:
            #                             datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
            #                         else:
            #                             datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
            #                         listforremoveappend(k)
            #                     else:
            #                         data = str(k) + " " + str(averagemaindict[k])
            #                         if "{" in k:
            #                             datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
            #                         else:
            #                             datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
            #                         listforremoveappend(k)
            #                     f.write(data)
            #                     f.write("\n")
            #                     f.write(datacv)
            #                     f.write("\n")
            #     else:
            #         sethelp = parseforsethelp(line)
            #         if parseforsetkeys(k).issuperset(sethelp):
            #             if mappingdict[k] not in checklist:
            #                 if strtype == "counter":
            #                     data = str(k) + " " + str(int(averagemaindict[k]))
            #                     if "{" in k:
            #                         datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
            #                     else:
            #                         datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
            #                     listforremoveappend(k)
            #                 else:
            #                     data = str(k) + " " + str(averagemaindict[k])
            #                     if "{" in k:
            #                         datacv = str(mappingdict[k])+"_CV{"+str(labeldict[k])+ " " + str(cvmaindict[k])
            #                     else:
            #                         datacv = str(mappingdict[k])+"_CV " + str(cvmaindict[k])
            #                     listforremoveappend(k)
            #             f.write(data)
            #             f.write("\n")
            #             f.write(datacv)
            #             f.write("\n")
       
        for items in listforremove:
            tempmaindict.pop(items)
        listforremove.clear()
    f.close
    if lastvaluefunction:
        lastmaindict=maindict.copy()
    end = time.process_time()
    timewriter("writetoafter"+ " "+ str(end-start))

def initmemory():
    start = time.process_time()
    maindict.clear()
    helplist.clear()
    checklist.clear()
    averagemaindict.clear()
    cvmaindict.clear()
    end = time.process_time()
    timewriter("cleardata" + " " + str(end-start))

def compressfile():
    start = time.process_time()
    with open('after', 'rb') as f_in, gzip.open('after.gz', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
    end = time.process_time()
    timewriter("compressfile" + " " + str(end-start))

if __name__ == "__main__":
    perparestart = time.process_time()
    scrapeurl=gettargets(getControllerMasterIP())
    clv=0

    BUFFER_SIZE = 16384
    HOST = '0.0.0.0'
    PORT = 54088
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)
    loop = asyncio.get_event_loop()
    perpareend = time.process_time()
    timewriter("perpare"+ " "+ str(perpareend - perparestart))
    while True:
        print("Server start")
        conn, addr = server.accept()
        clientMessage = str(conn.recv(1024), encoding='utf-8')
        start = time.process_time()
        if clientMessage == "acala":
            metricsstart = time.process_time()
            loop.run_until_complete(asyncgetmetrics(scrapeurl))
            metricsend = time.process_time()
            timewriter("getmetricsandmerge"+ " "+ str(metricsend-metricsstart))
            calcavg()
            rebuildfile(clv)
            compressfile()
            initmemory()
            sendstart = time.process_time()
            with open("after.gz", "rb") as f:
                while True:
                    bytes_read = f.read(BUFFER_SIZE)
                    if not bytes_read:
                        break
                    conn.sendall(bytes_read)
            conn.close()
            end = time.process_time()
            timewriter("send"+ " " + str(end-sendstart))
            timewriter("total"+ " " + str(end-start))
        elif clientMessage == "acala:1":
            lastmaindict.clear()
            metricsstart = time.process_time()
            loop.run_until_complete(asyncgetmetrics(scrapeurl))
            metricsend = time.process_time()
            timewriter("getmetricsandmerge"+ " "+ str(metricsend-metricsstart))
            calcavg()
            rebuildfile(clv)
            compressfile()
            initmemory()
            sendstart = time.process_time()
            with open("after.gz", "rb") as f:
                while True:
                    bytes_read = f.read(BUFFER_SIZE)
                    if not bytes_read:
                        break
                    conn.sendall(bytes_read)
            conn.close()
            end = time.process_time()
            timewriter("send"+ " " + str(end-sendstart))
            timewriter("total"+ " " + str(end-start))