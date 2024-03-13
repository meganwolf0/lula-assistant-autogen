from autogen import AssistantAgent, UserProxyAgent, GroupChat, GroupChatManager
from agents.kubectl_executor import CustomKubectlExecutorAgent
# from autogen.coding import LocalCommandLineCodeExecutor
import os
from dotenv import load_dotenv
load_dotenv()

config_list = [{"model": "gpt-4-0125-preview", "api_key": os.environ["OPENAI_API_KEY"]}]
llm_config = {
    "config_list": config_list,
}

# TODO: Move these to user input
TOOL = "Promtail"
CONTROL = """
"An event is any observable occurrence in an organizational information system. 
    Organizations identify audit events as those events which are significant and relevant to the security of information systems and the environments in which those systems operate in order to meet specific and ongoing audit needs. 
    Audit events can include, for example, password changes, failed logons, or failed accesses related to information systems, administrative privilege usage, PIV credential usage, or third-party credential usage. 
    In determining the set of auditable events, organizations consider the auditing appropriate for each of the security controls to be implemented. 
    To balance auditing requirements with other information system needs, this control also requires identifying that subset of auditable events that are audited at a given point in time."
"""

# Agent definitions 
user_proxy = UserProxyAgent(
    name="SystemExpert",
    system_message="A human admin to guide and provide-feedback.",
    code_execution_config={"last_n_messages": 2, "work_dir": "groupchat", "use_docker": False},
    human_input_mode="ALWAYS",
    # is_termination_msg=lambda x: x.get("content", "") and x.get("content", "").rstrip().endswith("TERMINATE"),
)

system_owner = UserProxyAgent(
    name="SystemOwner",
    system_message="System Owner who is responsible for the system and its compliance.",
    code_execution_config={"last_n_messages": 2, "work_dir": "groupchat", "use_docker": False},
    human_input_mode="NEVER",
    # is_termination_msg=lambda x: x.get("content", "") and x.get("content", "").rstrip().endswith("TERMINATE"),
)

term_msg = "" # "Reply `TERMINATE` in the end when everything is done."

control_expert = AssistantAgent(
    name="ControlExpert",
    system_message="Ingest control text and tool name, decompose the control text into functional requirements that can be satisfied by the tool {TOOL}. {term_msg}",
    llm_config=llm_config,
    description="""
    You are a systems thinker and have a deep understanding of the control. 
    You seek to reframe the control text into the context of what the tool {TOOL} can do.
    You provide concise and clear functional requirements that can be satisfied by the tool {TOOL}.
    """
)

kubernetes_expert = CustomKubectlExecutorAgent(
    name="KubernetesExpert",
    system_message="Determine all relevant Kubernetes resources to requirements and fetch and provide data from the Kubernetes cluster. {term_msg}",
    description="""
    Expert in Kubernetes and how various tools are installed in the cluster via Kubernetes-specific resources.
    Determine all relevant Kubernetes resources to requirements and fetch and provide data from the Kubernetes cluster.
    Provide all data as json output, this will be used as input by the RegoPolicyBuilder to write policies to validate
    the json data.

    To get more information about the Kubernetes system, you use the following tools:
    - get_cluster_resources: provides a json representation of all the Kubernetes resources
    in the cluster
    - get_named_resources: provides a json representation of the specific named Kubernetes resources of a 
    given type. Expects inputs of "resource_type" (string) and "namespace_scoped" (boolean).
    - get_resource: provides a json representation of a specific named Kubernetes resource. Expects input 
    string of the format "resource_type,resource_name,namespace" for a namespace-scoped resource, or 
    "resource_type,resource_name,none" for a cluster-scoped resource
    - base64_decode: decodes a base64 encoded string which may be in the Kubernetes resources, particularly secrets.
    Expects input as a base64 encoded string.
    For each custom tool, if tool results in an error, the returned string will start with "Error".
    """,
    code_execution_config={"last_n_messages": 2, "work_dir": "groupchat", "use_docker": False},
    config_list=config_list,
)

rego_policy_builder = AssistantAgent(
    name="RegoPolicyBuilder",
    system_message="Build a Rego policy to validate a functional requirement. {term_msg}",
    description="""
    Expert in Open Policy Agent (OPA) and the Rego policy language, you have a deep understanding of how to write 
    validation code to evaluate whether true or false satisfaction of data to requirements.
    You write thorough but concise policy statements that can be broken down into bite-sized chunks for the 
    KubernetesExpert to provide evidence.
    """,
    llm_config=llm_config,
)

evaluation_agent = AssistantAgent(
    name="EvaluationAgent",
    system_message="Evaluates the sets of kubernetes data and rego policies to ensure they are fully covering the functional requirement of the tool. {term_msg}",
    llm_config=llm_config,
    description="""
    You are a senior expert in the Kubernetes system and the tool. You have a sophisticated understanding
    of how the tool integrates with the Kubernetes system and how it satisfies a given control.

    You are concerned with clarity, accuracy, and completeness of the evidence provided to satisfy the control.
    You review the Kubernetes artifacts along with the Rego policy to ensure full coverage of the
    functional requirements are met. If you find policies and kubernetes artifacts insufficient to provide
    evidence of control satisfaction, you ask for additional kubernetes artifacts and rego policies.
    """
)

def _reset_agents():
    user_proxy.reset()
    system_owner.reset()
    control_expert.reset()
    kubernetes_expert.reset()
    rego_policy_builder.reset()
    evaluation_agent.reset()

agents_requirements = [user_proxy, control_expert, kubernetes_expert]
agents_implementation = [user_proxy, kubernetes_expert, rego_policy_builder, evaluation_agent]

# Background set-up - possibly to be moved to user input
control_text = """
    
"""
tool = "Promtail"

# initial_message = f"""I have a system I am trying to evaluate for control compliance. 
# I am specifically interested in evaluating the use of the tool {tool} in my system for the following control:
# {control_text}
# """

initial_message = f"""
Group of agents determined to fully evaluate the use of {TOOL} in their system to prove satisfaction of the following control: 
{CONTROL}
"""

# Task definitions
decompose_control = f"""
Decompose the control into functional requirements that can be realized by {TOOL}.

The control text is as follows:
{CONTROL}
"""

gather_artifacts = f"""
KubernetesExpert should perform the following:
- Retreive all cluster data in json that describes tool {TOOL} readiness.
- For each functional requirement, retreive all cluster data in json that describes tool {TOOL} 
configuration settings specific to satisfying the requirement.
"""

write_policy = f"""
Using the Kubernetes cluster data as json input, create one or many Rego policies to validate 
{TOOL} implementation aginst the requirement.
"""

find_evidence = f"""
{gather_artifacts}
{write_policy}
"""

review = f"""
Review the functional requirements and associated evidence an policies to establish the system meets requirements. 
Solicit additional iterations with the KubernetesExpert and RegoPolicyBuilder to build complete and thorough policies.
Consolidate the information from the previous tasks and generate a list of output sets:
Each set in the list should have the following items:
- description of the purpose of the particular policy - particularly which functional requirement is it intending to satisfy
- description of the expected input data
- rego policy with "package validation" header and "validation" variable that returns true or false
"""

# groupchat_message = [decompose_control, find_evidence, write_policy, review]
# groupchat_message = "Helpful group of several subject matter experts to evaluate the use of a tool in a system for a specific control."
groupchat_message = initial_message

# Group setup
groupchat_requirements = GroupChat(
    agents=agents_requirements, 
    messages=[], 
    max_round=3,
    # allow_repeat_speaker=True, # they just go back and forth forever
    speaker_selection_method="auto",
)
groupchat_manager_requirements = GroupChatManager(
    groupchat=groupchat_requirements, 
    system_message=groupchat_message,
    llm_config=llm_config, 
    human_input_mode="TERMINATE",
)

groupchat_implementation = GroupChat(
    agents=agents_implementation, 
    messages=[], 
    max_round=12,
    # allow_repeat_speaker=True,
    speaker_selection_method="auto",
)
groupchat_manager_implementation = GroupChatManager(
    groupchat=groupchat_implementation, 
    system_message=groupchat_message,
    llm_config=llm_config, 
    human_input_mode="TERMINATE",
)

# Initiate Chat
# user_proxy.initiate_chat(
#     groupchat_manager,
#     message=initial_message
# )
_reset_agents()
groupchat_implementation.reset()
groupchat_requirements.reset()
groupchat_manager_implementation.reset()
groupchat_manager_requirements.reset()

user_proxy.initiate_chats(
    [
        {
            "sender": system_owner,
            "recipient": groupchat_manager_requirements,
            "message": decompose_control,
            "clear_history": False,
            "silent": False,
            "summary_method": "reflection_with_llm",
            "summary_prompt": f"Provide a concise list of functional requirements derived from the control that can be realized by the tool {TOOL}"
        },
        {
            "sender": system_owner,
            "recipient": groupchat_manager_implementation,
            "message": find_evidence,
            "clear_history": False,
            "silent": False,
            "summary_method": "reflection_with_llm",
            "summary_prompt": """
                Consolidate the information gathered by the experts in this task into a list of outputs.
                Each item in the list should have the following details:
                - description of the purpose of the particular policy - particularly which functional requirement is it intending to satisfy
                - description of the expected input data
                - rego policy with "package validation" header and "validation" variable that returns true or false
            """
        },
        # {
        #     "sender": system_owner,
        #     "recipient": groupchat_manager_implementation,
        #     "message": write_policy,
        #     "clear_history": False,
        #     "silent": False,
        #     "summary_method": "reflection_with_llm",
        # },
        # {
        #     "sender": system_owner,
        #     "recipient": groupchat_manager_implementation,
        #     "message": review,
        #     "clear_history": False,
        #     "silent": False,
        #     "summary_method": "reflection_with_llm",
        # },
    ]
)
