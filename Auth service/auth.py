import random
import hashlib
import datetime
import jwt
import psycopg2


private_JWT_key = "Mortira Moraxa"
password_encryption_key = 'pushkatanka'


def custom_hasher(password):
    global password_encryption_key
    salt = password_encryption_key
    password = hashlib.sha256((password + salt).encode()).hexdigest()
    return password


def uid_generator():
    created_uid = ''.join(str(random.randint(0, 9)) for _ in range(12))
    email_check_query = "SELECT * FROM users WHERE uid = %s"
    cursor.execute(email_check_query, (created_uid,))
    checker = cursor.fetchone()
    if checker is None:
        return created_uid
    else:
        return uid_generator()


def email_validation(email):
    # todo Подтверждение почты
    confirmed = True
    if confirmed:
        return True
    else:
        return False


def email_check(p_email):
    email_check_query = "SELECT * FROM users WHERE email = %s"
    cursor.execute(email_check_query, (p_email,))
    result = cursor.fetchone()
    if result is None:
        return False
    else:
        return True


def token_generator(user_data, token_type):
    global private_JWT_key
    secret_key = private_JWT_key
    if token_type == 'refresh':
        lifetime = 96
    else:
        lifetime = 12
    payload = {
        "iss": 'Random_chats auth service',
        "token_type": token_type,
        "sub": user_data,
        "exp": datetime.datetime.utcnow() + datetime.timedelta(hours=lifetime)
    }
    token = jwt.encode(payload, secret_key, algorithm="HS256")
    return token


def send_token(token):
    pass
    # todo sending tokens via HTTP

def registration(splitted_string):
    email = splitted_string[0].strip()
    if email_check(email):
        return 'warning: email is already used'
    else:
        if email_validation(email):
            password = custom_hasher(splitted_string[1].strip())
            '''
            tuple structure: email - string up to 256 chars, password - string up to 256 chars (hashed with sha256),
            sex - string up to 10 chars, age - integer, preffered_age - string up to 7 chars, interests - text,
            uid - string 12 chars (see uid_generator) - PRIMARY_KEY, access_token - text (see token_generator), 
            refresh_key - text (see token_generator)
            splitted_string[2].strip() - sex
            splitted_string[3].strip() - age
            splitted_string[4].strip() - preffered_age
            splitted_string[5].strip() - interests
            '''
            new_user = (email, password, splitted_string[2].strip(), int(splitted_string[3].strip()),
                        splitted_string[4].strip(), splitted_string[5].strip(), uid_generator(),
                        None, None)

            try:
                insert_query = """
                    INSERT INTO users (email, password, sex, age, preffered_age, interests, uid, access_token, refresh_token)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.execute(insert_query, new_user)
                db_connection.commit()
                print('Запись создана')
            except Exception as e:
                print('error:', e)

            return 'success: new user has been registered'
        else:
            return 'warning: email is not confirmed'


def authorisation(splitted_string):
    email = splitted_string[0].strip()
    query = "SELECT * FROM users WHERE email = %s"
    cursor.execute(query, (email,))
    user = cursor.fetchone()
    if user is None:
        return 'warning: user with this email does not exist'
    else:
        stored_password = user[1]
        password = custom_hasher(splitted_string[1].strip())
        if password == stored_password:
            uid = user[6]
            user_new_data = (token_generator(uid, 'access'), token_generator(uid, 'refresh'))

            try:
                query = """
                UPDATE users
                SET access_token = %s,
                refresh_token = %s
                WHERE uid = %s
                """
                cursor.execute(query, (user_new_data[0], user_new_data[1], uid,))
                db_connection.commit()
            except Exception as ex:
                print('Error updating:', ex)

            send_token(user_new_data[0])
            send_token(user_new_data[1])
            return 'success: authorisation complete, tokens sent'
        else:
            return 'warning: incorrect password'


def authentification(in_token, ref_key):
    dec_token = jwt.decode(in_token, ref_key, algorithms="HS256")
    if dec_token['iss'] != 'Random_chats auth service':
        return 'Warning: false token'
    else:
        if dec_token is not None:
            if dec_token['token_type'] == 'access':
                if dec_token['exp'] < datetime.datetime.utcnow():
                    return 'Query: Send a refresh token'
                else:
                    return 'INFO: access token is up to date'

            else:
                if dec_token['exp'] < datetime.datetime.utcnow():
                    return 'Query: Required authorisation'
                else:
                    uid = dec_token['sub']
                    new_access_token = token_generator(uid, 'access')

                    try:
                        query = """
                                    UPDATE users
                                    SET access_token = %s
                                    WHERE uid = %s
                                    """
                        cursor.execute(query, (new_access_token, uid,))
                        db_connection.commit()
                    except Exception as ex:
                        print('Error updating:', ex)
                        return 'Warning: error updating token, try again'

                    send_token(new_access_token)
                    return 'INFO: Access token has been updated'
        else:
            return 'Warning: Token does not exist'


if __name__ == '__main__':
    db_connection, cursor = None, None
    # connecting to database and creating cursor
    try:
        db_connection = psycopg2.connect(
            dbname="auth_service",
            user="postgres",
            password="admin",
            host="localhost",
            port="5435"
        )
        print("База подключена успешно")
        try:
            cursor = db_connection.cursor()
            print("kursor sozdan")
        except Exception as e:
            print("Oshibka of kursor", e)

    except Exception as e:
        print("Oshibka of database:", e)


    q = "SELECT * FROM users WHERE email = %s"
    cursor.execute(q, ('test@example.com',))
    print(cursor.fetchone())
    '''
    When executing SELECT something FROM users WHERE condition, cursor will return tuple, some tuples with the following
    structure: (email (str), password hash (str), sex (str), age (int),
    preffered_age (str), interests (str), user id (str), access token (JWT, str), refresh token (JWT, str)
    '''
    while True:
        server_query = input('<-- ')
        # expected: 1000 email | password | sex | age | pref_age | interests
        if server_query[:4] == '1000':
            print('<--', registration(server_query[4:].split('|')))

        # expected: 1001 email | password
        if server_query[:4] == '1001':
            print('<--', authorisation(server_query[4:].split('|')))

        # expected: JWT
        if server_query[:4] == '1010':
            print('<-- refresh token received')
            refresh_token = server_query[4:].strip()
            print('-->', authentification(refresh_token, private_JWT_key))

        if server_query == '-100':
            # noinspection PyUnboundLocalVariable
            if cursor:
                # noinspection PyUnboundLocalVariable
                cursor.close()
            # noinspection PyUnboundLocalVariable
            if db_connection:
                # noinspection PyUnboundLocalVariable
                db_connection.close()

        if server_query == '-101':
            break

