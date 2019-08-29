import yaml
import tempfile
import shutil
import re
import subprocess
from utils.log import *
from utils.utils import *


class ocBase():
    """ """
    def __init__(self, options, base_config, testconfig, binary="oc"):
        self.kubeconfig = options.kubeconfig
        self.binary = binary        
        self.globalvars = {}

        # read values from command line
        self.globalvars["kubeconfig"] = options.kubeconfig
        self.globalvars["debugoption"] = options.debug
        self.globalvars["env"] = []
        
        # read values from .config.cfg
        self.globalvars["processes"] = base_config.getint('global', 'processes')
        self.globalvars["cleanoption"] = base_config.getboolean('global', 'cleanall')

        if "tuningsets" in testconfig:
            self.globalvars["tuningsets"] = testconfig["tuningsets"]

        for config in testconfig["projects"]:
            if "tuning" in config:
                self.globalvars["tuningset"] = self.find_tuning(testconfig["tuningsets"], config["tuning"])

        self.project_handler(config, self.globalvars)

    def get_system_admin(self, kubeconfig):
        ''' Retrieves the system admin '''
        with open(kubeconfig, 'r') as kubeconfig_file:
            config = yaml.load(kubeconfig_file)
            for user in config["users"]:
                if user["name"].startswith("system:admin"):
                    return user["name"]
        return False

    def oc_command(self, args, kubeconfig):
        print(kubeconfig)
        """Run the `oc` and return tuple with stdout, stderr, and return code"""
        tmpfile=tempfile.NamedTemporaryFile()
        # see https://github.com/openshift/origin/issues/7063 for details why this is done.
        shutil.copyfile(kubeconfig, tmpfile.name)
        cmd = "KUBECONFIG=" + tmpfile.name + " " + args
        print(cmd)
        process = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode != 0:
            logger.error("oc_command: {} :: Return Code: {}".format(cmd, process.returncode))
        else:
            logger.info("oc_command: {} :: Return Code: {}".format(cmd, process.returncode))
        #logger.debug("stdout: %s", str(stdout).strip())
        #logger.debug("stderr: %s", str(stderr).strip())
        tmpfile.close()
        return stdout, stderr, process.returncode

    def oc_command_with_retry(self, args, kubeconfig, max_retries=10, backoff_period=10):
        """Run the oc_command function but check returncode for 0, retry otherwise"""
        output = self.oc_command(args, kubeconfig)
        retry_count = 0
        while (output[2] != 0):
            if retry_count >= max_retries:
                logger.error("Unable to complete with {} retries".format(retry_count))
                break
            retry_count += 1
            retry_time = retry_count * backoff_period
            logger.warn("{} Retry of OC command in {}s".format(retry_count, retry_time))
            time.sleep(retry_time)
            output = self.oc_command(args, kubeconfig)
        return output

    def check_oc_version(self):
        major_version = 0
        minor_version = 0
        version_string = self.oc_command("oc version", self.kubeconfig)
        result = re.search("{} v(\d+)\.(\d+)\..*".format(self.binary), version_string[0])
        if result:
            major_version = result.group(1)
            minor_version = result.group(2)
        return {"major":major_version, "minor": minor_version}  


    def find_tuning(self, tuningsets, name):
        for tuningset in tuningsets:
            if tuningset["name"] == name:
                return tuningset
            else:
                continue
        logger.error("Failed to find tuningset: " + name + " Exiting.....")
        sys.exit()

    def create_service(self, servconfig, num, globalvars):
        #logger.debug("create_service function called")

        data = {}
        timings = {}
        data = servconfig
        i = 0
        while i < int(num):
            tmpfile=tempfile.NamedTemporaryFile()
            dataserv = copy.deepcopy(data)
            servicename = dataserv["metadata"]["name"] + str(i)
            dataserv["metadata"]["name"] = servicename
            json.dump(dataserv, tmpfile)
            tmpfile.flush()

            check = self.oc_command("oc create -f " + tmpfile.name, globalvars)
            i = i + 1
            del (dataserv)
            tmpfile.close()


    def create_pods(self, podcfg, num, storagetype, globalvars):
        #logger.debug("create_pods function called")

        namespace = podcfg["metadata"]["namespace"]
        data = {}
        timings = {}
        data = podcfg
        i = 0
        pend_pods = globalvars["pend_pods"]
        while i < int(num):
            tmpfile=tempfile.NamedTemporaryFile()
            datapod = copy.deepcopy(data)
            podname = datapod["metadata"]["name"] + str(i)
            datapod["metadata"]["name"] = podname
            globalvars["curprojenv"]["pods"].append(podname)
            json.dump(datapod, tmpfile)
            tmpfile.flush()

            check = self.oc_command("oc create -f " + tmpfile.name, globalvars)
            pend_pods.append(podname)

            if "tuningset" in self.globalvars:
                if "stepping" in self.globalvars["tuningset"]:
                    stepsize = self.globalvars["tuningset"]["stepping"]["stepsize"]
                    pause = self.globalvars["tuningset"]["stepping"]["pause"]
                    self.globalvars["totalpods"] = self.globalvars["totalpods"] + 1
                    total_pods_created = int(self.globalvars["totalpods"])
                    if total_pods_created % stepsize == 0 and self.globalvars["tolerate"] is False:
                        pod_data(globalvars)
                        time.sleep(calc_time(pause))
                if "rate_limit" in self.globalvars["tuningset"]:
                    delay = self.globalvars["tuningset"]["rate_limit"]["delay"]
                    time.sleep(calc_time(delay))

            i = i + 1
            del (datapod)
            tmpfile.close()


    def pod_data(self, globalvars):
        #logger.debug("pod_data function called")

        pend_pods = self.globalvars["pend_pods"]
        namespace = self.globalvars["namespace"]
        while len(pend_pods) > 0:
            getpods = self.oc_command("oc get pods -n " + namespace, self.globalvars)
            all_status = getpods[0].split("\n")

            size = len(all_status)
            all_status = all_status[1:size - 1]
            for status in all_status:
                fields = status.split()
                if fields[2] == "Running" and fields[0] in pend_pods:
                    pend_pods.remove(fields[0])
            if len(pend_pods) > 0:
                time.sleep(5)


    def create_rc(self, rc_config, num, globalvars):
        #logger.debug("create_rc function called")

        i = 0
        data = rc_config
        basename = rc_config["metadata"]["name"]

        while i < num:
            tmpfile=tempfile.NamedTemporaryFile()
            curdata = copy.deepcopy(data)
            newname = basename + str(i)
            self.globalvars["curprojenv"]["rcs"].append(newname)
            curdata["metadata"]["name"] = newname
            curdata["spec"]["selector"]["name"] = newname
            curdata["spec"]["template"]["metadata"]["labels"]["name"] = newname
            json.dump(curdata, tmpfile)
            tmpfile.flush()

            self.oc_command("oc create -f " + tmpfile.name, globalvars)
            i = i + 1
            del (curdata)
            tmpfile.close()


    def project_exists(self, projname):
        exists = False
        try :
            output = self.oc_command("oc" + " get project -o name " + projname, self.kubeconfig)[0].rstrip()
            if output.endswith(projname):
                exists = True
        except subprocess.CalledProcessError:
            pass

        return exists

    def delete_project(self, projname):
        self.oc_command("oc" + " delete project " + projname, self.kubeconfig)

        # project deletion is asynch from resource deletion. 
        # the command returns before project is really gone
        retries = 0
        while self.project_exists(projname) and (retries < 10):
            retries += 1
            logger.info("Project " + projname + " still exists, waiting 10 seconds")
            time.sleep(10)

        # not deleted after retries, bail out
        if self.project_exists(projname) :
            raise RuntimeError("Failed to delete project " + projname)

    def single_project(self, testconfig, projname, globalvars):
        self.globalvars["createproj"] = True
        if self.project_exists(projname):
            if testconfig["ifexists"] == "delete":
                self.delete_project(projname)
            elif testconfig["ifexists"] == "reuse":
                self.globalvars["createproj"] = False
            else:
                logger.error("Project " + projname + " already exists. Use ifexists=reuse/delete in config")
                return

        if self.globalvars["createproj"]:    
            if 'nodeselector' in testconfig:
                node_selector = " --node-selector=\"" + testconfig['nodeselector'] + "\""
                self.oc_command_with_retry("oc adm new-project " + projname + node_selector, self.kubeconfig)
            else:
                self.oc_command_with_retry("oc new-project " + projname, self.kubeconfig)
            self.oc_command_with_retry("oc label --overwrite namespace " + projname +" purpose=test", self.kubeconfig)

        time.sleep(1)
        projenv={}

        if "tuningset" in self.globalvars:
            tuningset = self.globalvars["tuningset"]
        if "tuning" in testconfig:
            projenv["tuning"] = testconfig["tuning"]
        self.globalvars["curprojenv"] = projenv
        self.globalvars["namespace"] = projname
        if "quota" in testconfig:
            self.quota_handler(testconfig["quota"],self.globalvars)
        if "templates" in testconfig:
            self.template_handler(testconfig["templates"], self.globalvars)
        if "services" in testconfig:
            self.service_handler(testconfig["services"], self.globalvars)
        if "users" in testconfig:
            self.user_handler(testconfig["users"], self.globalvars)
        if "pods" in testconfig:
            if "pods" in tuningset:
                self.globalvars["tuningset"] = tuningset["pods"]
            self.pod_handler(testconfig["pods"], self.globalvars)
        if "rcs" in testconfig:
            self.rc_handler(testconfig["rcs"], self.globalvars)

    def project_handler(self, testconfig, globalvars):
        #logger.debug("project_handler function called")

        total_projs = testconfig["num"]
        basename = testconfig["basename"]
        self.globalvars["env"] = []
        maxforks = self.globalvars["processes"]

        projlist = []
        i = 0
        while i < int(total_projs):
            j=0
            children = []
            while j < int(maxforks) and i < int(total_projs):
                j=j+1
                pid = os.fork()
                if pid:
                    children.append(pid)
                    i = i + 1
                else:
                    projname = basename
                    if "ifexists" not in testconfig:
                        logger.info("Parameter 'ifexists' not specified. Using 'default' value.")
                        testconfig["ifexists"] = "default"
                    if testconfig["ifexists"] != "reuse" :
                        projname = basename + str(i)

                    logger.info("forking %s"%projname)
                    self.single_project(testconfig, projname, globalvars)
                    os._exit(0)
            for k, child in enumerate(children):
                os.waitpid(child, 0)


    def create_template(self, templatefile, num, parameters, globalvars):
        #logger.debug("create_template function called")

        parameter_flag = "-p"
        data = {}
        timings = {}
        i = 0
        while i < int(num):
            tmpfile=tempfile.NamedTemporaryFile()
            templatejson = copy.deepcopy(data)
            cmdstring = "oc process -f %s" % templatefile
            if parameters:
                for parameter in parameters:
                    for key, value in parameter.iteritems():
                        cmdstring += " " + parameter_flag + " %s='%s'" % (key, value)
            cmdstring += " " + parameter_flag + " IDENTIFIER=%i" % i

            processedstr = self.oc_command_with_retry(cmdstring, self.kubeconfig)
            templatejson = json.loads(processedstr[0])
            json.dump(templatejson, tmpfile)
            tmpfile.flush()
            check = self.oc_command_with_retry("oc create -f "+ tmpfile.name + \
                " --namespace %s" % self.globalvars["namespace"], self.kubeconfig)
            if "tuningset" in self.globalvars:
                if "templates" in self.globalvars["tuningset"]:
                    templatestuningset = self.globalvars["tuningset"]["templates"]
                    if "stepping" in templatestuningset:
                        stepsize = templatestuningset["stepping"]["stepsize"]
                        pause = templatestuningset["stepping"]["pause"]
                        self.globalvars["totaltemplates"] = self.globalvars["totaltemplates"] + 1
                        templates_created = int(self.globalvars["totaltemplates"])
                    if templates_created % stepsize == 0:
                        time.sleep(calc_time(pause))
                    if "rate_limit" in templatestuningset:
                        delay = templatestuningset["rate_limit"]["delay"]
                        time.sleep(calc_time(delay))
            i = i + 1
            tmpfile.close()

    def template_handler(self, templates, globalvars):
        #logger.debug("template_handler function called")
        logger.info("templates: %s", templates)
        for template in templates:
            num = int(template["num"])
            templatefile = template["file"]

            if "parameters" in template:
                parameters = template["parameters"]
            else:
                parameters = None
            if "tuningset" in self.globalvars:
                if "templates" in self.globalvars["tuningset"]:
                    if "stepping" in self.globalvars["tuningset"]["templates"]:
                        self.globalvars["totaltemplates"] = 0

            self.create_template(templatefile, num, parameters, globalvars)

        if "totaltemplates" in self.globalvars:
            del (self.globalvars["totaltemplates"])


    def service_handler(self, inputservs, globalvars):
        #logger.debug("service_handler function called")

        namespace = self.globalvars["namespace"]
        self.globalvars["curprojenv"]["services"] = []

        for service in inputservs:
            num = int(service["num"])
            servfile = service["file"]
            basename = service["basename"]

            service_config = {}
            with open(servfile) as stream:
                service_config = json.load(stream)
            service_config["metadata"]["namespace"] = namespace
            service_config["metadata"]["name"] = basename

            create_service(service_config, num, self.globalvars)


    def pod_handler(self, inputpods, globalvars):
        #logger.debug("pod_handler function called")

        namespace = self.globalvars["namespace"]
        total_pods = int(inputpods[0]["total"])
        inputpods = inputpods[1:]
        storage = inputpods[0]["storage"]

        global storagetype

        if storage[0]["type"] in ("none", "None", "n"):
            storagetype = storage[0]["type"]
            print ("If storage type is set to None, then pods will not have persistent storage")

        self.globalvars["curprojenv"]["pods"] = []
        if "tuningset" in self.globalvars:
            self.globalvars["podtuningset"] = self.globalvars["tuningset"]

        self.globalvars["pend_pods"] = []
        if "podtuningset" in self.globalvars:
            if "stepping" in self.globalvars["podtuningset"]:
                self.globalvars["totalpods"] = 0

        for podcfg in inputpods:
            num = int(podcfg["num"]) * total_pods / 100
            podfile = podcfg["file"]
            basename = podcfg["basename"]

            pod_config = {}
            with open(podfile) as stream:
                pod_config = json.load(stream)
            pod_config["metadata"]["namespace"] = namespace
            pod_config["metadata"]["name"] = basename

            create_pods(pod_config, num,storagetype, self.globalvars)

        if self.globalvars["tolerate"] is False:
            if len(self.globalvars["pend_pods"]) > 0:
                pod_data(self.globalvars)

            if "podtuningset" in self.globalvars:
                del(self.globalvars["podtuningset"])
                del(self.globalvars["totalpods"])
            del(self.globalvars["pend_pods"])


    def rc_handler(self, inputrcs, globalvars):
        #logger.debug("rc_handler function called")

        namespace = self.globalvars["namespace"]
        self.globalvars["curprojenv"]["rcs"] = []
        for rc_cfg in inputrcs:
            num = int(rc_cfg["num"])
            replicas = int(rc_cfg["replicas"])
            rcfile = rc_cfg["file"]
            basename = rc_cfg["basename"]
            image = rc_cfg["image"]

            rc_config = {}
            with open(rcfile) as stream:
                rc_config = json.load(stream)
            rc_config["metadata"]["namespace"] = namespace
            rc_config["metadata"]["name"] = basename
            rc_config["spec"]["replicas"] = replicas
            rc_config["spec"]["template"]["spec"]["containers"][0]["image"] = image

            create_rc(rc_config, num, self.globalvars)

