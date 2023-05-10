import yaml
from langchain import PromptTemplate, SerpAPIWrapper
from langchain.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.agents import ZeroShotAgent, Tool
from config import ModelConfig
from apps.database.pubsub import PubsubChatLog
import os
from langchain.output_parsers import PydanticOutputParser, OutputFixingParser, RetryOutputParser
from pydantic import BaseModel, Field, validators

class Preprocess:
    '''
    Prompt Template에 담길 기본 Prompt를 작성한다. (history, input 제외 나머지)
    '''

    def __init__(self):
        self.template = self.load_template()

    def persona(self, tplt, persona:str="친절한 상담원"):
        '''
        Args:
            - persona(string): 사용자가 입력한 persona 정보
        Returns:
            - __(string) persona 정보가 담긴 prompt
        '''
        res = tplt["persona"]["default"]
        if persona == "시니컬한 고양이":
            res = tplt["persona"]["cat"]
        elif persona == "지혜로운 노인":
            res = tplt["persona"]["elder"]

        return res
    
    
    def user_info(self, tplt, user_info:dict):
        '''
        Args:
            - user_info(dict): 사용자가 입력한 user 정보
        Returns:
            - __(string): user 정보가 담긴 prompt
        '''

        user_tplt = tplt["user_info"]
        name = user_info["user_info_name"]
        age = user_info["user_info_age"]
        sex = user_info["user_info_sex"]
        job = user_info["user_info_job"]
        hobby = user_info["user_info_hobby"]

        rules = {"name":name, "age":age, "sex":sex, "job":job, "hobby":hobby}

        return user_tplt.format(**rules)
    
    def load_yaml(self, dir):
        with open(dir, encoding='utf8') as f:
            res =yaml.load(f, Loader=yaml.FullLoader)
        return res

    def load_template(self, dir = "apps/models/prompt/prompt_template.yaml"):
        tmpl = self.load_yaml(dir)
        return tmpl
    
    

class Prompt(Preprocess):
    '''
    기본 Prompt + History + Input = Prompt Template
    '''
        
    def __init__(self):
        super().__init__()
        self.tplt = self.template["default"]

    def write_prompt(self, persona:str, user_info:dict):
        '''
        Args:
            - persona(str): 사용자가 입력한 persona 정보
            - user_info(dict): 사용자가 입력한 user 정보
        Returns:
            - prompt(ChatPromptTemplate): ConversationChain에 담길 Prompt
        '''

        # LOGGING
        PubsubChatLog.publish('프롬프트 생성 ing...........')

        input_variables = ["history"]

        chat_prompt = PromptTemplate(
            input_variables = input_variables,
            template = self.tplt["instruction"] + self.persona(tplt=self.tplt, persona=persona) + self.user_info(tplt=self.tplt, user_info=user_info) + self.tplt["base"]
            )
        
        prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate(prompt=chat_prompt),
                HumanMessagePromptTemplate.from_template("{input}")
                ])

        # LOGGING
        log =  self.tplt["instruction"] + self.persona(tplt=self.tplt, persona=persona)
        PubsubChatLog.publish('프롬프트 생성 완료!')
        PubsubChatLog.publish(log)

        return prompt
    

class BrowsePrompt(Preprocess):
    '''
    기본 Prompt + Agent + History + Input = Agent Prompt Template
    '''
        
    def __init__(self):
        super().__init__()
        self.tplt = self.template["browse"]
        self.params ={
            "engine": "google",
            "hl": "ko",
            "gl": "kr"
        }
        self.search = SerpAPIWrapper(params=self.params, serpapi_api_key = ModelConfig.SERP.API_KEY)
        self.tools = [
            Tool(
                name = "Search",
                func= self.search.run,
                description="useful for when you need to answer questions about current events"
            )
        ]

    def write_prompt(self, persona:str, user_info:dict):
        '''
        Args:
            - persona(dict): 사용자가 입력한 persona 정보
            - user_info(dict): 사용자가 입력한 user 정보
        Returns:
            - prompt(ChatPromptTemplate): ConversationChain에 담길 Prompt
        '''

        # LOGGING
        PubsubChatLog.publish('프롬프트 생성 ing...........')

        input_variables = ["history", "input", "agent_scratchpad"]
        
        suffix_info = {"persona":self.persona(tplt=self.tplt, persona=persona), 
                       "user_info":self.user_info(tplt=self.tplt, user_info=user_info)}

        suffix =  self.tplt["suffix"].format(**suffix_info) + self.tplt["base"]

        chat_prompt = ZeroShotAgent.create_prompt(
                self.tools, 
                prefix=self.tplt["prefix"],
                suffix=suffix,
                input_variables=input_variables
            )
        
        # LOGGING
        log = self.tplt["prefix"] + suffix
        PubsubChatLog.publish('프롬프트 생성 완료!')
        PubsubChatLog.publish(log)

        return chat_prompt
    
    
class DocsPrompt(Preprocess):
    '''
    기본 Prompt + Context +  Input = Prompt Template
    '''
        
    def __init__(self):
        super().__init__()
        self.tplt = self.template["docs"]

    def write_prompt(self, persona:str, user_info:dict):
        '''
        Args:
            - persona(str): 사용자가 입력한 persona 정보
        Returns:
            - prompt(ChatPromptTemplate): RetrievalQA에 담길 Prompt
        '''

        # LOGGING
        PubsubChatLog.publish('프롬프트 생성 ing...........')

        
        system_info = {"persona":self.persona(tplt=self.tplt, persona=persona), 
                       "user_info":self.user_info(tplt=self.tplt, user_info=user_info),
                       "context":"{context}"}
        system_prompt =  self.tplt["instruction"].format(**system_info)        
        
        input_variables = ["context"]

        chat_prompt = PromptTemplate(
            input_variables = input_variables,
            template = system_prompt
            )
        
        prompt = ChatPromptTemplate.from_messages([
                SystemMessagePromptTemplate(prompt=chat_prompt),
                HumanMessagePromptTemplate.from_template("{question}")
                ])

        # LOGGING
        log = system_prompt
        PubsubChatLog.publish('프롬프트 생성 완료!')
        PubsubChatLog.publish(log)

        return prompt