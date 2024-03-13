from autogen import UserProxyAgent
import subprocess
import sys
import json
import base64
from typing import Callable, Dict, List, Literal, Optional, Union

class CustomKubectlExecutorAgent(UserProxyAgent):
    def __init__(
            self, 
            name:str, 
            system_message: Optional[Union[str, List]] = "", 
            code_execution_config: Optional[Union[Dict, Literal[False]]] = None, 
            config_list: Optional[List[Dict]] = None,
            human_input_mode: Optional[str] = "NEVER",
            description: Optional[str] = None,
        ):
        """
        Custom agent for executing various kubectl commands to extract data from a Kubernetes cluster.

        Usage:
        - get_cluster_resources: get a list of all the Kubernetes resources in the cluster
        - get_named_resources: get a list of all the Kubernetes resources in the cluster
        - get_resource: get a single named resource from the cluster
        """
        function_map = {
            "get_cluster_resources": self.get_cluster_resources,
            "get_named_resources": self.get_named_resources,
            "get_resource": self.get_resource,
            "base64_decode": self.base64_decode,
        }

        custom_functions = [
            {   
                "name": "get_cluster_resources",
                "description": "A funciton to get a list of all the Kubernetes resources in the cluster. Takes no arguments.",
            },
            {
                "name": "get_named_resources",
                "description": "A function to get a list of named resources from a Kubernetes cluster. Takes two string arguments: resource_type and namespace_scoped.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_type": {
                            "type": "string",
                            "description": "The api kind of Kubernetes resource, e.g., deployments, pods, nodes"
                        },
                        "namespace_scoped": {
                            "type": "boolean",
                            "description": "Whether the resource is namespace-scoped, e.g., true or false"
                        },
                    },
                    "required": ["resource_type", "namespace_scoped"],
                }
            },
            {
                "name": "get_resource",
                "description": "A function to get a single named resource from a Kubernetes cluster. Takes three string arguments: resource_type, resource_name, and namespace.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_type": {
                            "type": "string",
                            "description": "The api kind of Kubernetes resource, e.g., deployments, pods, nodes"
                        },
                        "resource_name": {
                            "type": "string",
                            "description": "The name of the resource to get"
                        },
                        "namespace": {
                            "type": "string",
                            "description": "The namespace of the resource, or 'none' for cluster-scoped resources"
                        },
                    },
                    "required": ["resource_type", "resource_name", "namespace"],
                }
            },
            {
                "name": "base64_decode",
                "description": "A generic tool to decode a base64 encoded string",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_str": {
                            "type": "string",
                            "description": "Base64 encoded string to decode"
                        },
                    },
                    "required": ["input_str"],
                }
            }
        ]

        llm_config = {
            "functions": custom_functions,
            "config_list": config_list,
        }
        super().__init__(
            name=name, 
            system_message=system_message, 
            code_execution_config=code_execution_config, 
            llm_config=llm_config, 
            function_map=function_map, 
            human_input_mode=human_input_mode,
            description=description,
        )

    def get_cluster_resources(self) -> str:
        """ A generic tool to extract all api resources from a Kubernetes cluster as string json """

        command = r"""
        kubectl api-resources | awk 'NR>1 {if (NF==5) print $1","$2","$3","$4","$5; else if (NF==4) print $1",,"$2","$3","$4}' | jq -R -s -c 'split("\n") | 
        map(select(length > 0) | split(",") | {resource: .[0], shortNames: .[1], apiGroup: .[2], namespaced: .[3], kind: .[4]})'
        """

        try:
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            print(f"Error executing kubectl command: {e.stderr}", file=sys.stderr)
        except json.JSONDecodeError as e:
            print(f"Error decoding JSON output: {e.msg}", file=sys.stderr)

    def get_named_resources(self, resource_type: str, namespace_scoped: bool) -> str:
        """ A generic tool to extract named resources from a Kubernetes cluster based on input parameters """

        if namespace_scoped:
            command = r"""kubectl get %s --all-namespaces -o json | jq '[.items[] | {name: .metadata.name, namespace: .metadata.namespace}]'""" % resource_type
        else:
            command = r"""kubectl get %s -o json | jq '[.items[] | {name: .metadata.name}]'""" % resource_type

        try:
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            return f"Error executing kubectl command for {resource_type}: {e.stderr}"

    def get_resource(self, resource_type: str, resource_name: str, namespace: str) -> str:
        """ A generic tool to extract a single named resource from a Kubernetes cluster based on input parameters """

        if namespace == "none":
            command = f"kubectl get {resource_type} {resource_name} -o json"
        else:
            command = f"kubectl get {resource_type} {resource_name} -n {namespace} -o json"

        try:
            result = subprocess.run(command, shell=True, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            return result.stdout
        except subprocess.CalledProcessError as e:
            return f"Error executing kubectl command for {resource_type} named {resource_name} in namespace {namespace}: {e.stderr}"
    
    def base64_decode(self, input_str: str) -> str:
        """ A generic tool to decode a base64 encoded string """
        try:
            decoded_str = base64.b64decode(input_str).decode('utf-8')
            return decoded_str
        except base64.binascii.Error as e:
            return "Error: Input string is not valid base64 encoded text."
        except UnicodeDecodeError as e:
            return "Error: Decoded text could not be converted to UTF-8."