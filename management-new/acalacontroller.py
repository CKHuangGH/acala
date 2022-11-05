import gzip
import time
from requests import post
from kubernetes import config
import kubernetes.client
import logging
import asyncio

ipdict={}
portdict={}
timedict={}
resources = {}
scrapetime = {}
scrapelist=[]
timeout_seconds = 30

logging.basicConfig(level=logging.INFO)

def getControllerMasterIP():
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    master_ip = ""
    try:
        nodes = api_instance.list_node(pretty=True, _request_timeout=timeout_seconds)
        nodes = [node for node in nodes.items if
                 'node-role.kubernetes.io/master' in node.metadata.labels]
        # get all addresses of the master
        addresses = nodes[0].status.addresses

        master_ip = [i.address for i in addresses if i.type == "InternalIP"][0]
    except:
        print("Connection timeout after " + str(timeout_seconds) + " seconds to host cluster")

    return master_ip

def timewriter(text):
    try:
        f = open("exectime_management", 'a')
        f.write(text+"\n")
        f.close()
    except:
        print("Write error")

def posttogateway(clustername,instance, name):
    start = time.perf_counter()
    gateway_host="127.0.0.1"
    gateway_port="9091"
    url = "http://" + str(gateway_host) + ":" + str(gateway_port) + "/metrics/job/" + clustername + "/instance/" + instance
    res = post(url=url,data=name,headers={'Content-Type': 'application/octet-stream'})
    end = time.perf_counter()
    timewriter("posttogateway" + " " + str(end-start))

def parse_ip_port_name(data):
    origdata = data.strip('\n')
    parseddata = origdata.split(":")
    return str(parseddata[0]), int(parseddata[1]), str(parseddata[2])

def read_member_cluster():
    f = open("/root/member", 'r')
    for line in f.readlines():
        ip, port, cluster=parse_ip_port_name(line)
        scrapelist.append(ip)
        ipdict[cluster]=ip
        portdict[cluster]=port
        timedict[cluster]=0

async def fetch(link, clientMessage, number):
    print('Send: %r' % clientMessage)
    transtimestart = time.perf_counter()
    reader, writer = await asyncio.open_connection(link, 31580)
    #reader, writer = await asyncio.open_connection(link, 54088)
    writer.write(clientMessage.encode())
    
    rawmetrics = bytearray()
    while True:
        bytes_read = await reader.read(BUFFER_SIZE)
        if not bytes_read:
            break
        rawmetrics += bytes_read

    metrics = gzip.decompress(rawmetrics)
    writer.close()
    clustername="cluster"+str(number+1)
    transtimeend = time.perf_counter()
    timewriter("scrapeanddecompress" + " " + str(transtimeend-transtimestart))
    try:
        posttogateway(clustername,ipdict[clustername],metrics)
    except:
        print("post-fail")
        return "post-fail"
        
async def tcp_echo_client(links,clientMessage):
    tasks = [asyncio.create_task(fetch(link, clientMessage,links.index(link))) for link in links]
    try:
        fail=await asyncio.gather(*tasks)
        if fail[0]=="post-fail":
            return "acala:1"
        else:
            return "acala"
    except:
        print("oneofthem-fail")    
        return "acala"

if __name__ == "__main__":
    perparestart = time.perf_counter()
    read_member_cluster()
    clientMessage = "acala:1"
    BUFFER_SIZE=16324
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    perpareend = time.perf_counter()
    timewriter("perpare" + " " + str(perpareend-perparestart))
    while True:
        totaltimestart = time.perf_counter()
        clientMessage=loop.run_until_complete(tcp_echo_client(scrapelist,clientMessage))
        totaltimeend = time.perf_counter()
        timewriter("onescrapetotaltime" + " " + str(totaltimeend-totaltimestart))
        time.sleep(5)