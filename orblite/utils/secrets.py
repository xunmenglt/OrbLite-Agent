import string
import random

def generate_random_id(length=8):
    # 定义候选字符集：包含大小写字母和数字
    characters = string.ascii_letters + string.digits
    # 随机采样并拼接
    return ''.join(random.choices(characters, k=length))