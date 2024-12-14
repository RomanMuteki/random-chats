from pydantic import BaseModel, Field
from bson import ObjectId
from datetime import datetime
from typing import List, Dict, Optional


class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError('Недопустимый ObjectId')
        return ObjectId(v)


class MessageCreate(BaseModel):
    chat_id: str
    sender_id: str
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MessageStatusUpdate(BaseModel):
    receiver_id: str
    status: str  # Например, 'delivered', 'read'
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatCreate(BaseModel):
    participants: List[str]  # Список user_id участников


class Chat(BaseModel):
    id: PyObjectId = Field(alias="_id")
    participants: List[str]
    created_at: datetime
    last_message: Optional[Dict] = None
    # participants_names: List[str]

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class Message(BaseModel):
    id: PyObjectId = Field(alias="_id")
    chat_id: PyObjectId
    sender_id: str
    content: str
    timestamp: datetime
    status: Dict[str, Dict] = {}

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}


# from pydantic import BaseModel, Field
# from bson import ObjectId
# from datetime import datetime
# from typing import List, Dict, Optional
#
# # Кастомный валидатор для ObjectId
# class PyObjectId(ObjectId):
#     @classmethod
#     def __get_validators__(cls):
#         yield cls.validate
#
#     @classmethod
#     def validate(cls, v):
#         if not ObjectId.is_valid(v):
#             raise ValueError('Недопустимый ObjectId')
#         return ObjectId(v)
#
# class MessageCreate(BaseModel):
#     chat_id: str  # Принимаем chat_id как строку
#     sender_id: str
#     content: str
#     timestamp: datetime = Field(default_factory=datetime.utcnow)
#
# class MessageStatusUpdate(BaseModel):
#     receiver_id: str
#     status: str  # Например, 'delivered', 'read'
#     timestamp: datetime = Field(default_factory=datetime.utcnow)
#
# class ChatCreate(BaseModel):
#     participants: List[str]  # Список user_id участников
#     last_message: Optional[Dict] = None
#     status: Dict[str, str] = {}
#
# class Chat(BaseModel):
#     participants: List[str]
#     created_at: datetime
#     last_message: Optional[Dict] = None
#     status: Dict[str, str] = {}  # Статус доставки для каждого участника
#     id: PyObjectId = Field(alias="_id")
#
#     class Config:
#         allow_population_by_field_name = True
#         arbitrary_types_allowed = True
#         json_encoders = {ObjectId: str}
#
# class Message(BaseModel):
#     id: PyObjectId = Field(alias="_id")
#     chat_id: PyObjectId
#     sender_id: str
#     content: str
#     timestamp: datetime
#     status: Dict[str, Dict] = {}
#
#     class Config:
#         allow_population_by_field_name = True
#         arbitrary_types_allowed = True
#         json_encoders = {ObjectId: str}
