from typing import Annotated

import uvicorn
from sqlalchemy.orm import Session
from sqlalchemy import create_engine, select
import os
from hashlib import sha256
from uuid import uuid4
from fastapi import FastAPI, Cookie, Request, Form
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from model import Base, User, Book, SessionID

app = FastAPI()
html = Jinja2Templates(directory="html")
NDATABASE_URL=postgresql://neondb_owner:npg_VZuRle4yc3MY@ep-nameless-rice-apjhbeu1-pooler.c-7.us-east-1.aws.neon.tech/neondb?channel_binding=require&sslmode=require
DATABASE_URL = os.environ.get(NDATABASE_URL)

engine = create_engine(DATABASE_URL)
Base.metadata.create_all(engine)


@app.get("/")
def index(request: Request, session_id: Annotated[str | None, Cookie()] = None):
    with Session(engine) as session:
        user = None
        if session_id:
            session_id = session.get(SessionID, session_id)
            if session_id:
                user = session.get(User, session_id.user_id)
        books = session.scalars(select(Book)).all()
        return html.TemplateResponse(request, "index.html", {
            'books': books, 'user': user
        })


@app.get("/form")
def form(request: Request):
    return html.TemplateResponse(request, "add.html")


@app.get("/login_form")
def form(request: Request):
    return html.TemplateResponse(request, "login.html")


@app.get("/reg_form")
def form(request: Request):
    return html.TemplateResponse(request, "reg.html")


@app.get("/book/{id}")
def form(request: Request):
    return html.TemplateResponse(request, "books.html")


@app.post("/add")
def add(
        title: Annotated[str, Form()],
        author: Annotated[str, Form()],
        year: Annotated[int, Form()],
        session_id: Annotated[str, Cookie()] = None
):
    if not session_id:
        return "Войдите, чтобы добавить книгу"

    with Session(engine) as session:
        # 1. Используем другое имя переменной, чтобы не затереть число из куки
        db_session = session.get(SessionID, session_id)

        # 2. Проверяем, нашелся ли объект в базе данных
        if not db_session:
            return "Войдите, чтобы добавить книгу"

        session.add(Book(
            title=title,
            author=author,
            year=year,
            added_by=db_session.user_id  # 3. Берем ID юзера из объекта базы данных
        ))
        session.commit()

    return RedirectResponse("/", status_code=302)


@app.get("/delete/{id}")
def delete(
        id: int,
        session_id: Annotated[str, Cookie()] = None
):
    if session_id is None:
        return 'Войдите, чтобы удалить книгу'

    with Session(engine) as session:
        # Получаем сессию из базы данных
        db_session = session.get(SessionID, session_id)
        if not db_session:
            return 'Войдите, чтобы удалить книгу'

        # Получаем пользователя и проверяем права
        user = session.get(User, db_session.user_id)
        if not user or not user.is_admin:
            return "Только админ может удалить книгу"

        # Находим книгу по ID
        book = session.get(Book, id)
        if not book:
            return "Книга не найдена"

        # Удаляем книгу
        session.delete(book)
        session.commit()

    # Важно: используем статус 303 для перехода после GET/POST запросов
    return RedirectResponse("/", status_code=303)


@app.post("/reg")
def reg(
        login: Annotated[str, Form()],
        password: Annotated[str, Form()],
        password2: Annotated[str, Form()]
):
    if password != password2:
        return "Пароли не совпадают"
    with Session(engine) as session:
        if session.scalars(select(User).where(User.login == login)).one_or_none():
            return "Пользователь с таким логином уже существует"
        password = sha256(password.encode('utf-8')).hexdigest()
        session.add(User(
                login=login,
                password=password
        ))
        session.commit()
    return RedirectResponse("/login_form",status_code=302)


@app.post("/login")
def login(
        login: Annotated[str, Form()],
        password: Annotated[str, Form()]
):
    with Session(engine) as session:
        user = session.scalars(select(User).where(User.login == login)).one_or_none()
        if not user:
            return "Такого пользователя нет"
        password = sha256(password.encode('utf-8')).hexdigest()
        if user.password != password:
            return "Пароль неверный"
        session_id = str(uuid4())
        session.add(SessionID(id=session_id, user_id=user.id))
        session.commit()
    response = RedirectResponse("/", status_code=302)
    response.set_cookie('session_id', session_id)
    return response

    response = RedirectResponse("/", status_code=302)
    response.set_cookie("login", login)
    return response


@app.get('/set_admin/{login}')
def set_admin(login: str):
    with Session(engine) as session:
        user = session.scalars(select(User).where(User.login == login)).one_or_none()
        user.is_admin = True
        session.add(user)
        session.commit()
    return RedirectResponse("/", status_code=302)


@app.get('/book/{id}')
def book_id(
        request: Request,
        id: int,
        session_id: Annotated[str, Cookie()] = None
):
    if not session_id:
        return "Войдите, чтобы посмотреть информацию о книге"

    with Session(engine) as session:
        # 1. Заменили имя на db_session, чтобы код не падал
        db_session = session.get(SessionID, session_id)
        if not db_session:
            return "Войдите, чтобы посмотреть информацию о книге"

        user = session.get(User, db_session.user_id)

        # 2. Получаем книгу из базы
        book = session.get(Book, id)

        # 3. ДОБАВИЛИ ПРОВЕРКУ: если книги нет, прерываем работу
        if not book:
            return "Книга не найдена в базе данных"

        added_by = session.get(User, book.added_by)

        return html.TemplateResponse(request, 'books.html', {
            'book': book,
            'added_by': added_by,
            'is_admin': user.is_admin
        })


@app.get("/logout")
def logout(session_id: Annotated[str | None, Cookie()] = None):
    # Если куки и так нет, просто отправляем на главную
    if not session_id:
        return RedirectResponse("/", status_code=302)

    with Session(engine) as session:
        # Ищем сессию в базе данных
        db_session = session.get(SessionID, session_id)
        if db_session:
            # Удаляем сессию, чтобы токен стал недействительным
            session.delete(db_session)
            session.commit()

    # Создаем редирект на главную страницу
    response = RedirectResponse("/", status_code=302)
    # Удаляем куки из браузера
    response.delete_cookie("session_id")
    return response

if __name__ == '__main__':
    uvicorn.run(app)
