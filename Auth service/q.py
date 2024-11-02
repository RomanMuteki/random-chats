'''data = [
    {'name': 'Alice', 'email': 'alice@example.com'},
    {'name': 'Bob', 'email': 'bob@example.com'},
    {'name': 'Charlie', 'email': 'charlie@example.com'},
]
email_index = {d['email']: d for d in data}

# Поиск словаря по email
result = email_index.get('bob@example.com')

if result:
    print("Найденный словарь:", result)
else:
    print("Словарь с таким email не найден.")
print(result['name'])'''

import hashlib

passw = input('pw: ').encode()
salt = 'pushkatanka'.encode()
passw1 = hashlib.sha256(passw).hexdigest()
passw2 = hashlib.sha256(passw+salt).hexdigest()
print(passw1, passw2)