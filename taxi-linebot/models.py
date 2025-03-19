from pymongo import MongoClient
from config import Config

client = MongoClient(Config.MONGO_URI)
db = client.get_database()

class User:
    def __init__(self, line_user_id, name, phone, destination=None, passengers=1):
        self.line_user_id = line_user_id
        self.name = name
        self.phone = phone
        self.destination = destination
        self.passengers = passengers

    def save(self):
        db.users.insert_one({
            'line_user_id': self.line_user_id,
            'name': self.name,
            'phone': self.phone,
            'destination': self.destination,
            'passengers': self.passengers
        })

    @staticmethod
    def find_by_line_user_id(line_user_id):
        return db.users.find_one({'line_user_id': line_user_id})

class Match:
    def __init__(self, group_id, leader_id, members):
        self.group_id = group_id
        self.leader_id = leader_id
        self.members = members

    def save(self):
        db.matches.insert_one({
            'group_id': self.group_id,
            'leader_id': self.leader_id,
            'members': self.members
        })

    @staticmethod
    def find_by_group_id(group_id):
        return db.matches.find_one({'group_id': group_id})
