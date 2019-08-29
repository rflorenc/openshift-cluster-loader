# OCP cluster-loader
This package is written in python and can be used to stress an OpenShift installation.
It uses a placement nodeSelector to create projects containing stress pods.

You can run any application you would like inside your stress pods.

e.g.: `logger`, `stress`, `fallocate`, `curl`, `dd`, `jmeter`.


## Steps

### Log in to OCP
```
oc login https://openshift-master.ose1.helvetia-devl.io --token=${token}
```

### Label your target node(s)
```
oc label node ip-xx-xxx-xxx-xxx.eu-central-1.compute.internal placement=stress
oc label node ip-yy-yyy-yyy-yyy.eu-central-1.compute.internal placement=logtest
```

### Sample run

```
 $ python cluster-loader.py -f config/ocp-logtest.yaml

```