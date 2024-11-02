import random
import hashlib
import datetime
import jwt


def custom_hasher(password):
    salt = 'pushkatanka'
    password = hashlib.sha256((password + salt).encode()).hexdigest()
    return password


def uid_generator():
    global uid_index
    uid = ''.join(str(random.randint(0, 9)) for _ in range(12))
    checker = uid_index.get(uid)
    if checker is None:
        return uid
    else:
        return uid_generator()


def email_validation(email):
    # todo Подтверждение почты
    confirmed = True
    if confirmed:
        return True
    else:
        return False


def email_check(email):
    global email_index
    result = email_index.get(email)
    if result is None:
        return False
    else:
        return True


def token_generator(user_data, token_type):
    # todo token generation and storing to ./tokens with returning path to it
    secret_key = 'Mortira Moraxa'
    if token_type == 'refresh':
        lifetime = 96
    else:
        lifetime = 12
    payload = {
        "iss": 'Random_chats auth service',
        "sub": user_data,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=lifetime)
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def registration(splitted_string):
    global bd, email_index

    email = splitted_string[0].strip()
    if email_check(email):
        return 'warning: email is already used'
    else:
        if email_validation(email):
            password = custom_hasher(splitted_string[1].strip())

            new_user = {'email': email, 'password': password,
                        'sex': splitted_string[2].strip(), 'age': splitted_string[3].strip(),
                        'preferred_age': splitted_string[4].strip(), 'interests': splitted_string[5].strip(),
                        'uid': uid_generator(), 'access token': None, 'refresh token': None}
            bd.append(new_user)
            email_index = {d['email']: d for d in bd}
            return 'success: new user has been registered'
        else:
            return 'warning: email is not confirmed'


def authorisation(splitted_string):
    global bd, email_index

    email = splitted_string[0].strip()
    if email_check(email):
        stored_password = email_index.get(email)['password']
        password = custom_hasher(splitted_string[1].strip())
        if password == stored_password:
            uid = email_index.get(email)['uid']
            user_data = {**email_index.get(email), 'access token': token_generator(uid, 'access'),
                         'refresh token': token_generator(uid, 'refresh')}
            bd[bd.index(email_index[email])] = user_data
            return 'success: authorisation complete, tokens sent'
        else:
            return 'warning: incorrect password'
    else:
        return 'warning: user with this email does not exist'


def authentification(ref_token):
    pass


bd = [{'email': 'a@mail.ru', 'password': 'b30f370f4bfb62ec1cc6b4951440490a6f7146086e50882bd9e0c583e7e60aa9',
       'sex': 'male', 'age': 22, 'preferred_age': '19-23',
       'interests': 'nthng', 'uid': '00000000000', 'access token': None, 'refresh token': None}]
email_index = {d['email']: d for d in bd}
uid_index = {d['uid']: d for d in bd}

if __name__ == '__main__':
    print(bd)
    while True:
        query = input('<-- ')
        if query[:4] == '1000':
            print('<--', registration(query[4:].split('|')))

        if query[:4] == '1001':
            print('<--', authorisation(query[4:].split('|')))

        if query[:4] == '1002':
            print('<-- refresh token received')
            refresh_token = query[4:].strip()
            print('-->', authentification(refresh_token))

        print('\n', bd)
