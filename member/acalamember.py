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


timeout_seconds = 30
maindict = {}
timesdict = {}
helplist = []
checklist = []
lastmaindict = {}

logging.basicConfig(level=logging.INFO)

def timewriter(text):
    try:
        f = open("exectime", 'a')
    except:
        print("Open exectime failed")
    try:
        f.write(text)
        f.write("\n")
        f.close
    except:
        print("Write error")

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
    parseddata = textline.split("{")
    return str(parseddata[0])

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

    return str(parseddata[1])

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
    start = time.perf_counter()
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
    end = time.perf_counter()
    timewriter("gettargets" + " " + str(end-start))
    return scrapeurl

def getmetrics(url):
    start = time.perf_counter()
    prom_url = url
    session = requests.Session()
    prom_header = {'Accept-Encoding': 'gzip'}
    r = session.get(url=prom_url, headers=prom_header)
    fname = "before"
    f = open(fname, 'w')
    f.write(r.text)
    f.close
    end = time.perf_counter()
    timewriter("getmetrics" + " " + str(end-start))

async def fetch(link, session,number):
    try:
        async with session.get(link) as response:
            html_body = await response.text()
            fname = "before" + str(number)
            f = open(fname, 'w')
            f.write(html_body)
            f.close
    except:
        print("get metrics failed")


async def asyncgetmetrics(links):
    async with ClientSession() as session:
        tasks = [asyncio.create_task(fetch(link, session, links.index(link))) for link in links]  # 建立任務清單
        await asyncio.gather(*tasks)

def merge(path):
    start = time.perf_counter()
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
    for line in f.readlines():
        if line[0] == "#":
            if counterformetrics % 2 == 0:
                if line not in helplist:
                    helplistappend(line)
                    checklistappend(parseforstrhelp(line))
            counterformetrics += 1
        else:
            valuelistappend(parsevalue(line))
            metricsnameappend(parsename(line))

    if not maindict:
        maindict = dict(zip(metricsname, valuelist))
        for k in maindict.keys():
            timesdict.setdefault(k, 1.0)
    else:
        tempdict = dict(zip(metricsname, valuelist))
        for k, v in tempdict.items():
            if k in maindict.keys():
                maindict[k] = float(maindict[k])+float(v)
                timesdict[k] = float(timesdict[k]) + 1.0
            else:
                maindict[k] = float(v)
                timesdict.setdefault(k, 1.0)
    f.close()
    end = time.perf_counter()
    timewriter("merge" + " " + str(end-start))

def calcavg():
    start = time.perf_counter()
    for k in maindict.keys():
        if k in timesdict.keys():
            maindict[k] = float(maindict[k])/float(timesdict[k])
    end = time.perf_counter()
    timewriter("calcavg" + " " + str(end-start))

def rebuildfile(lastvaluefunction):
    start = time.perf_counter()
    global lastmaindict
    fname = "after"
    f = open(fname, 'w')
    tempmaindict = maindict.copy()
    mappingdict={}
    listforremove = []
    listforremoveappend = listforremove.append

    for k in maindict.keys():
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
                                data = str(k) + " " + str(int(maindict[k]))
                                listforremoveappend(k)
                            else:
                                data = str(k) + " " + str(maindict[k])
                                listforremoveappend(k)
                            if flag:
                                f.write(line)
                                flag=0
                            f.write(data)
                            f.write("\n")
                    else:
                        if strtype == "counter":
                            data = str(k) + " " + str(int(maindict[k]))
                            listforremoveappend(k)
                        else:
                            data = str(k) + " " + str(maindict[k])
                            listforremoveappend(k)
                        if flag:
                            f.write(line)
                            flag=0
                        f.write(data)
                        f.write("\n")
                else:
                    if strtype == "counter":
                        data = str(k) + " " + str(int(maindict[k]))
                        listforremoveappend(k)
                    else:
                        data = str(k) + " " + str(maindict[k])
                        listforremoveappend(k)
                    if flag:
                        f.write(line)
                        flag=0
                    f.write(data)
                    f.write("\n")
            elif strtype == "summary" or strtype=="histogram":
                if strtype=="histogram":
                    if flag:
                        f.write(line)
                        flag=0
                if lastvaluefunction:
                    sethelp = parseforsethelp(line)
                    if parseforsetkeys(k).issuperset(sethelp):
                        if mappingdict[k] not in checklist:
                            if lastmaindict:
                                if tempmaindict[k] != lastmaindict[k]:
                                    if strtype == "counter":
                                        data = str(k) + " " + str(int(maindict[k]))
                                        listforremoveappend(k)
                                    else:
                                        data = str(k) + " " + str(maindict[k])
                                        listforremoveappend(k)
                                    f.write(data)
                                    f.write("\n")
                            else:
                                if strtype == "counter":
                                    data = str(k) + " " + str(int(maindict[k]))
                                    listforremoveappend(k)
                                else:
                                    data = str(k) + " " + str(maindict[k])
                                    listforremoveappend(k)
                                f.write(data)
                                f.write("\n")
                else:
                    sethelp = parseforsethelp(line)
                    if parseforsetkeys(k).issuperset(sethelp):
                        if mappingdict[k] not in checklist:
                            if strtype == "counter":
                                data = str(k) + " " + str(int(maindict[k]))
                                listforremoveappend(k)
                            else:
                                data = str(k) + " " + str(maindict[k])
                                listforremoveappend(k)
                        f.write(data)
                        f.write("\n")
        for items in listforremove:
            tempmaindict.pop(items)
        listforremove.clear()
    f.close
    lastmaindict=maindict.copy()
    end = time.perf_counter()
    timewriter("writetoafter"+ " "+ str(end-start))

def initmemory():
    start = time.perf_counter()
    maindict.clear()
    timesdict.clear()
    helplist.clear()
    checklist.clear()
    end = time.perf_counter()
    timewriter("cleardata" + " " + str(end-start))

def compressfile():
    start = time.perf_counter()
    with open('after', 'rb') as f_in, gzip.open('after.gz', 'wb') as f_out:
        shutil.copyfileobj(f_in, f_out)
    end = time.perf_counter()
    timewriter("compressfile" + " " + str(end-start))

if __name__ == "__main__":
    perparestart = time.perf_counter()

    prom_host=getControllerMasterIP()
    scrapeurl=gettargets(prom_host)
    lenoftarget=len(scrapeurl)
    clv=1

    BUFFER_SIZE = 8192
    HOST = '0.0.0.0'
    PORT = 54088
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((HOST, PORT))
    server.listen(1)

    perpareend = time.perf_counter()
    timewriter("perpare"+ " "+ str(perpareend - perparestart))
    while True:
        print("Server start")
        conn, addr = server.accept()
        clientMessage = str(conn.recv(1024), encoding='utf-8')
        start = time.perf_counter()
        loop = asyncio.get_event_loop()
        if clientMessage == "rntsm":
            metricsstart = time.perf_counter()
            loop.run_until_complete(asyncgetmetrics(scrapeurl))
            metricsend = time.perf_counter()
            timewriter("getmetrics"+ " "+ str(metricsend-metricsstart))
            for number in range(lenoftarget):
                #getmetrics(url)
                name= "before" + str(number)
                merge(name)
            calcavg()
            rebuildfile(clv)
            initmemory()
            compressfile()
            sendstart = time.perf_counter()
            with open("after.gz", "rb") as f:
                while True:
                    bytes_read = f.read(BUFFER_SIZE)
                    if not bytes_read:
                        break
                    conn.sendall(bytes_read)
            end = time.perf_counter()
            conn.close()
            timewriter("send"+ " " + str(end-sendstart))
            timewriter("total"+ " " + str(end-start))
        elif clientMessage == "rntsm:1":
            lastmaindict.clear()
            metricsstart = time.perf_counter()
            loop.run_until_complete(asyncgetmetrics(scrapeurl))
            metricsend = time.perf_counter()
            timewriter("getmetrics"+ " "+ str(metricsend-metricsstart))
            for number in range(lenoftarget):
                #getmetrics(url)
                name= "before" + str(number)
                merge(name)
            calcavg()
            rebuildfile(clv)
            initmemory()
            compressfile()
            sendstart = time.perf_counter()
            with open("after.gz", "rb") as f:
                while True:
                    bytes_read = f.read(BUFFER_SIZE)
                    if not bytes_read:
                        break
                    conn.sendall(bytes_read)
            end = time.perf_counter()
            conn.close()
            timewriter("send"+ " " + str(end-sendstart))
            timewriter("total"+ " " + str(end-start))