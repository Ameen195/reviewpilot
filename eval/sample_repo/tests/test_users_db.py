from shop.users_db import add_user, connect, count_users, delete_user, find_by_email, get_user


def test_add_and_get():
    conn = connect()
    uid = add_user(conn, "Ana", "ana@example.com")
    assert get_user(conn, uid) == {"id": uid, "name": "Ana", "email": "ana@example.com"}
    assert get_user(conn, 999) is None


def test_find_and_delete():
    conn = connect()
    uid = add_user(conn, "Bo", "bo@example.com")
    assert find_by_email(conn, "bo@example.com") == [{"id": uid, "name": "Bo"}]
    delete_user(conn, uid)
    assert count_users(conn) == 0
