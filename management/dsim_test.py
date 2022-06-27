from kubernetes import client, config
from kubernetes.client.rest import ApiException
import yaml
import kubernetes.client
import base64
from prometheus_api_client import PrometheusConnect
import requests
import sys
import time

timeout_seconds=30
clusters = []
scrapetime = {}
resources = {}

def getsecretname():
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    namespace="monitoring"
    label_selector="app=kube-prometheus-stack-prometheus-scrape-confg"

    try:
        resp=api_instance.list_namespaced_secret(namespace=namespace, label_selector=label_selector,timeout_seconds=timeout_seconds)
    except:
        print("Connection timeout after " + str(timeout_seconds) + " seconds to host cluster")
    
    return resp.items[0].metadata.name

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

def getcurrentclusters():
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    namespace="monitoring"
    label_selector="app=kube-prometheus-stack-prometheus-scrape-confg"

    try:
        resp=api_instance.list_namespaced_secret(namespace=namespace, label_selector=label_selector,timeout_seconds=timeout_seconds)
        config_base64=resp.items[0].data['additional-scrape-configs.yaml']
        config_decode=base64.b64decode(config_base64)
        yaml_config=yaml.full_load(config_decode.decode())
        for item in yaml_config:
            clusters.append(item['job_name'])
    except:
        print("Connection timeout after " + str(timeout_seconds) + " seconds to host cluster")
        
def reloadapi():
    prom_host = getControllerMasterIP()
    prom_port = 9090
    prom_url = "http://" + str(prom_host) + ":" + str(prom_port) + "/-/reload"
    print(prom_url)
    r = requests.post(url = prom_url)


def decidetime(cluster):
    current=resources[cluster]
    if current < 40:
        answer=(m*current)+b
        print(answer)
        time="'" + str(int(answer))+"s'"
        scrapetime[cluster]=time
        

def getsecret():
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    namespace="monitoring"
    name=getsecretname()

    resp=api_instance.read_namespaced_secret(name=name, namespace=namespace)
    return resp

def updateSecret(code):
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    secret = getsecret()
    namespace="monitoring"
    name = getsecretname()
    print(secret)
    secret.data['additional-scrape-configs.yaml'] = code
    print(secret)
    api_instance.patch_namespaced_secret(name=name, namespace=namespace, body=secret)
    reloadapi()

def modifyconfig():
    config.load_kube_config()
    api_instance = kubernetes.client.CoreV1Api()
    secret = getsecret()
    config_base64=secret.data['additional-scrape-configs.yaml']
    config_decode=base64.b64decode(config_base64)
    yaml_config=yaml.full_load(config_decode.decode())
    for item in yaml_config:
        item['scrape_interval']=scrapetime[item['job_name']]
    config_encode=base64.b64encode(str(yaml_config).encode("utf-8"))
    encodedStr=config_encode.decode("UTF-8")
    code=encodedStr
    updateSecret(code)

def getresources(mode):
    prom_host = getControllerMasterIP()
    prom_port = 30090
    prom_url = "http://" + str(prom_host) + ":" + str(prom_port)
    getcurrentclusters()
    pc = PrometheusConnect(url=prom_url, disable_ssl=True)

    for cluster in clusters:
        if mode == "CPU" or mode == 'cpu':
            query="(avg(instance:node_cpu_utilisation:rate5m{cluster_name='" + cluster + "'})*100)"
            result = pc.custom_query(query=query)
            if len(result) > 0:
                resources[cluster] = float(result[0]['value'][1])
                decidetime(cluster)
        elif mode == "Memory" or mode == 'memory':
            query="(avg(instance:node_memory_utilisation:ratio{cluster_name='" + cluster + "'})*100)"
            result = pc.custom_query(query=query)
            if len(result) > 0:
                resources[cluster] = float(result[0]['value'][1])
                decidetime(cluster)
        else:
            print("Please input cpu or Memory")
    #modifyconfig()

def getformule(minlevel, timemax, maxlevel, timemin):
    global m
    m=(int(timemin)-int(timemax))/(int(maxlevel)-int(minlevel))
    global b
    b=(float(timemax)-(m*float(minlevel)))

if __name__ == "__main__":
    minlevel = sys.argv[1]
    timemax = sys.argv[2]
    maxlevel = sys.argv[3]
    timemin = sys.argv[4]
    checktime = sys.argv[5]
    resourcetype = sys.argv[6]
    getformule(minlevel, timemax, maxlevel, timemin)
    while 1:
        getresources(resourcetype)
        time.sleep(int(checktime))