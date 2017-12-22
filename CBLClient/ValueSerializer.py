import json

from MemoryPointer import MemoryPointer

class ValueSerializer:
    @staticmethod
    def serialize(value):
        if value is None:
            return "null"
        elif isinstance(value, MemoryPointer):
            return value.getAddress()
        elif isinstance(value, str):
            string = str(value)
            return "\"" + string + "\""
        elif isinstance(value, unicode):
            value = value.encode('utf-8')
            return "\"" + value + "\""
        elif isinstance(value, bool):
            bool_val = bool(value)
            return "true" if bool_val else "false"
        elif isinstance(value, int):
            number = int(value)
            return "I" + str(number)
        elif isinstance(value, float):
            number = float(value)
            return "F" + str(number)
        elif isinstance(value, long):
            number = long(value)
            return "L" + str(number)
        # There is no double/number in python
        elif isinstance(value, dict):
            dict_map = value
            stringMap = {}

            for map_param in dict_map:
                val = ValueSerializer.serialize(dict_map[map_param])
                stringMap[map_param] = val

            return json.dumps(stringMap)
            # return json.dumps(value)
        elif isinstance(value, list):
            stringList = []

            for obj in value:
                string = ValueSerializer.serialize(obj)
                stringList.append(string)

            return json.dumps(stringList)

        raise RuntimeError("Invalid value type: {}: {}".format(value, type(value)))

    @staticmethod
    def deserialize(value):
        if not value or len(value) == 0 or value == "null":
            return None
        elif value.startswith("@"):
            return MemoryPointer(value)
        elif value.startswith("\"") and value.endswith("\""):
            return value[1:-1]
        elif value == "true":
            return True
        elif value == "false":
            return False
        elif value.startswith("I"):
            return int(value[1:])
        elif value.startswith("L"):
            return long(value[1:])
        elif value.startswith("F") or value.startswith("D"):
            return float(value[1:])
        elif value.startswith("#"):
            if "." in value:
                return float(value[1:])
            else:
                return int(value[1:])
        elif value.startswith("{"):
            stringMap = json.loads(value)
            dict_map = {}
            for entry in stringMap:
                key = str(entry)
                obj = ValueSerializer.deserialize(stringMap[key])

                dict_map[key] = obj
            return dict_map
        elif value.startswith("["):
            stringList = json.loads(value)
            res_list = []

            for string in stringList:
                obj = ValueSerializer.deserialize(str(string))
                res_list.append(obj)

            return res_list

        raise RuntimeError("Invalid value type: {}: {}".format(value, type(value)))