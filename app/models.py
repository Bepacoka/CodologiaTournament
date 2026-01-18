#app/models.py
from datetime import datetime, timezone, timedelta
from .extensions import db
from enum import Enum
from werkzeug.security import generate_password_hash, check_password_hash

from sqlalchemy.dialects.postgresql import ENUM as PgEnum
from sqlalchemy import UniqueConstraint, Index, text

class Team(db.Model):
    __tablename__ = "teams"
    id = db.Column(db.Integer, primary_key=True)

    # название команды
    name = db.Column(db.String(200), nullable=False)

    # пароль (хешированный)
    password_hash = db.Column(db.String(255), nullable=False)

    # участники команды
    member1 = db.Column(db.String(100), nullable=False)
    member2 = db.Column(db.String(100), nullable=True)
    member3 = db.Column(db.String(100), nullable=True)

    # привязка к турниру (команда регистрируется на один турнир)
    tournament_id = db.Column(db.Integer, db.ForeignKey("tournaments.id"), nullable=False)
    tournament = db.relationship("Tournament", backref=db.backref("teams", lazy="dynamic"))
    
    # время начала турнира для этой команды
    started_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # ответы команды
    answers = db.relationship("Answer", back_populates="team", cascade="all, delete-orphan")
    
    def set_password(self, password):
        """Устанавливает пароль команды (хеширует его)"""
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        """Проверяет пароль команды"""
        return check_password_hash(self.password_hash, password)

    # Flask-Login compatibility (поведение прежнее)
    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


class Task(db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    text = db.Column(db.Text, nullable=False)
    type = db.Column(db.String, default="single")  # "single" или "examples"
    examples = db.relationship("TaskExample", backref="task", cascade="all, delete-orphan", order_by="TaskExample.id")
    image_url = db.Column(db.String(500))
    correct_answer = db.Column(db.String(200), nullable=True)  # для single задач
    points = db.Column(db.Integer, default=1)
    order = db.Column(db.Integer)

    # Связь к ответам
    answers = db.relationship("Answer", back_populates="task", cascade="all, delete-orphan")
    block_id = db.Column(
        db.Integer,
        db.ForeignKey("task_blocks.id"),
        nullable=False
    )
    block = db.relationship("TaskBlock", backref=db.backref("tasks", order_by="Task.order", lazy=True))


class TaskExample(db.Model):
    __tablename__ = "task_examples"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    text = db.Column(db.String, nullable=False)              # текст примера
    correct_answer = db.Column(db.String, nullable=False)    # корректный ответ как строка
    points = db.Column(db.Integer, nullable=True)            # если null => берём правило начисления (или 0)

    # task relationship via backref defined in Task


class Answer(db.Model):
    __tablename__ = "answers"
    id = db.Column(db.Integer, primary_key=True)

    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)

    # example_id NULL означает ответ на всю задачу; иначе ответ на конкретный пример
    example_id = db.Column(db.Integer, db.ForeignKey("task_examples.id"), nullable=True)

    answer_text = db.Column(db.String(200), nullable=False)
    is_correct = db.Column(db.Boolean, nullable=False, default=False)
    points = db.Column(db.Integer, nullable=True, default=0)

    submitted_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    # связи
    team = db.relationship("Team", back_populates="answers")
    task = db.relationship("Task", back_populates="answers")
    example = db.relationship("TaskExample", uselist=False)

    # SQLAlchemy-level unique constraints:
    # - уникальность для пар (team_id, task_id, example_id) — защищает дублирование по конкретному примеру
    # - для whole-task (example_id IS NULL) мы создадим partial index (см. миграции/SQL)
    __table_args__ = (
        UniqueConstraint("team_id", "task_id", "example_id", name="uq_answers_team_task_example"),
    )


class Tournament(db.Model):
    __tablename__ = "tournaments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)

    # группа/класс — произвольная метка
    group = db.Column(db.String(32), nullable=True, index=True)


class TaskBlock(db.Model):
    __tablename__ = "task_blocks"

    id = db.Column(db.Integer, primary_key=True)

    tournament_id = db.Column(
        db.Integer,
        db.ForeignKey("tournaments.id"),
        nullable=False
    )

    name = db.Column(db.String(64), nullable=False)
    order = db.Column(db.Integer, nullable=False)  # порядок блока в турнире
    max_duration = db.Column(db.Integer, nullable=False)  # максимальная длительность в секундах
    image_url = db.Column(db.String(500), nullable=True)   # картинка для отображения в правом нижнем углу

    tournament = db.relationship("Tournament", backref=db.backref("blocks", order_by="TaskBlock.order", lazy=True))

class TeamBlockStart(db.Model):
    """
    Время начала блока для конкретной команды.
    Устанавливается когда команда нажимает кнопку "Начать следующий блок".
    """
    tablename = "team_block_starts"
    
    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False)
    block_id = db.Column(db.Integer, db.ForeignKey("task_blocks.id"), nullable=False)
    started_at = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    team = db.relationship("Team", backref=db.backref("block_starts", lazy="dynamic"))
    block = db.relationship("TaskBlock", backref=db.backref("team_starts", lazy="dynamic"))
    
    table_args = (
        UniqueConstraint("team_id", "block_id", name="uq_team_block_start"),
    )

def reset_db():
    Answer.query.delete()
    TaskExample.query.delete()
    Task.query.delete()
    TeamBlockStart.query.delete()
    TaskBlock.query.delete()
    Team.query.delete()
    Tournament.query.delete()
    db.session.commit()



def create_tour():

    for i in range(5, 0, -1):
        tour = Tournament(name=f"Математический триатлон, {i} класс")
        if i <= 2:
            block1 = TaskBlock(name="Задачи", order=2, max_duration=2100, tournament=tour, image_url="alice2.png")
            task1 = Task(
                title="№1",
                order=1,
                text="Из самого маленького двузначного числа вычли самое большое однозначное, что получилось?",
                correct_answer="1",
                block=block1, 
                points=3
            )
            task2 = Task(
                title="№2",
                order=2,
                text="Два одинаковых числа сложили, и получилось двузначное число, записанное одинаковыми цифрами. Чему равно получившиеся число, если оно самое маленькое из возможных?",
                correct_answer="22",
                block=block1, 
                points=4
            )
            task3 = Task(
                title="№3",
                order=3,
                text="Миша купил линейку и карандаш и заплатил 14 рублей, а Паша купил ручку за 8 рублей. Сколько рублей надо заплатить за ручку, линейку и карандаш?",
                correct_answer="22",
                block=block1, 
                points=3
            )
            task4 = Task(
                title="№4",
                order=4,
                text="Миша купил 2 линейки и карандаш и заплатил 17 рублей, а Паша купил карандаш и 2 ручки и заплатил 26 рублей. Сколько стоит 2 линейки, 2 карандаша и 2 ручки?",
                correct_answer="43",
                block=block1, 
                points=4
            )
            task5 = Task(
                title="№5",
                order=5,
                text="В поход ходили класс 3Б, где 27 учеников, и класс 4А, где 24 ученика. Если мальчиков было 25, то сколько девочек пошло в поход?",
                correct_answer="26",
                block=block1, 
                points=3
            )
            task6 = Task(
                title="№6",
                order=6,
                text="Близнецы Маша и Саша одного роста. Петя выше Маши, а Боря ниже Саши. Кто выше: Петя или Боря?",
                correct_answer="Петя",
                block=block1, 
                points=3
            )
            task7 = Task(
                title="№7",
                order=7,
                text="У Кати 7 пятерок по математике, и это на 3 пятерки меньше, чем у Вики. Сколько всего пятерок вместе у девочек?",
                correct_answer="17",
                block=block1, 
                points=3
            )
            task8 = Task(
                title="№8",
                order=8,
                text="Маша заработала 3 пятерки, ее подруга Катя на 2 пятерки больше, а Миша на 4 пятерки меньше чем Катя и Маша вместе. Сколько пятерок у Маши?",
                correct_answer="3",
                block=block1, 
                points=4
            )
            task9 = Task(
                title="№9",
                order=9,
                text="Если Маша отдаст Злате три ручки, то у них будет поровну ручек. Сколько ручек у Маши, если всего ручек 10?",
                correct_answer="8",
                block=block1, 
                points=3
            )
            task10 = Task(
                title="№10",
                order=10,
                text="На сколько изменится сумма, если первое слагаемое увеличится на 5, а второе слагаемое уменьшится на 3? Ввести только число, например 10",
                correct_answer="2",
                block=block1, 
                points=4
            )
            task11 = Task(
                title="№11",
                order=11,
                text="Елка весит 2кг и еще половину елки. Сколько весит елка с игрушками, если игрушки отдельно весят 1 кг.",
                correct_answer="5",
                block=block1, 
                points=4
            )
            task12 = Task(
                title="№12",
                order=12,
                text="У Маши есть капибара длиной 30см, а у Кати есть медведь длиной 40см. Маша решила узнать какая высота елки в капибарах, а Катя замерила высоту елки медведями. И у Маши и у Кати получилось целое количество зверей. Какая высота елки в сантиметрах, если они больше 1 метра и меньше 2 метров?",
                correct_answer="120",
                block=block1, 
                points=3
            )

            block2 = TaskBlock(name="Геометрия", order=3, max_duration=2100, tournament=tour, image_url="alice3.png")
            task13 = Task(
                title="№1",
                order=1,
                text="У квадрата срезали один угол, сколько углов стало у получившейся фигуры?",
                correct_answer="5",
                block=block2, 
                points=3
            )
            task14 = Task(
                title="№2",
                order=2,
                text="Большой куб состоит из 27 маленьких белых кубиков. Какое минимальное количество кубиков надо заменить на черные, чтобы с каждой стороны большого куба видно было черный кубик?",
                correct_answer="2",
                block=block2, 
                points=3
            )
            task15 = Task(
                title="№3",
                order=3,
                text="Сколько треугольников на картинке?",
                correct_answer="18",
                image_url="task1.png",
                block=block2, 
                points=3
            )
            task16 = Task(
                title="№4",
                order=4,
                text="Красный большой деревянный куб разрезали на 27 маленьких. Сколько получилось кубиков, не окрашенных в красный цвет?",
                correct_answer="1",
                block=block2, 
                points=3
            )
            task17 = Task(
                title="№5",
                order=5,
                text="Из каких пентамино собрана фигура? В ответе указать номера пентамино в порядке возрастания без пробела. Например, если номера 11 и 12, то записать 1112.",
                correct_answer="17",
                image_url='task2.png',
                block=block2, 
                points=3
            )
            task18 = Task(
                title="№6",
                order=6,
                text="Из каких пентамино собрана фигура? В ответе указать номера пентамино в порядке возрастания без пробела. Например, если номера 11 и 12, то записать 1112.",
                correct_answer="2612",
                image_url='task8.png',
                block=block2, 
                points=4
            )
            task19 = Task(
                title="№7",
                order=7,
                text="Из некоторых наборов фигур (снизу) собрали картинки (сверху). Какие наборы остались не использованы? В ответе ввести числа в порядке возрастания без пробела, например 910.",
                correct_answer="35",
                image_url='task4.png',
                block=block2, 
                points=3
            )
            task20 = Task(
                title="№8",
                order=8,
                text="В стене образовалась дыра. Сколько кирпичей понадобится для ремонта?",
                correct_answer="9",
                image_url='task5.png',
                block=block2, 
                points=3
            )
            task21 = Task(
                title="№9",
                order=9,
                text="Разноцветный квадрат повернули несколько раз, как на картинке. Какая цифра будет на месте вопросительного знака?",
                correct_answer="3",
                image_url='task6.png',
                block=block2, 
                points=3
            )

            block3 = TaskBlock(name="Примеры", order=1, max_duration=600, tournament=tour, image_url="alice1.png")
            task22 = Task(
                title="№1",
                text="",
                type="examples",
                order=1,
                block=block3,
                examples=[
                    TaskExample(text="7 + 8 = ", correct_answer="15", points=1),
                    TaskExample(text="6 + 5 = ", correct_answer="11", points=1),
                    TaskExample(text="8 + 8 = ", correct_answer="16", points=1),
                    TaskExample(text="9 + 7 = ", correct_answer="16", points=1),
                    TaskExample(text="5 + 8 = ", correct_answer="13", points=1),
                    TaskExample(text="4 + 9 = ", correct_answer="13", points=1),
                    TaskExample(text="7 + 6 = ", correct_answer="13", points=1),
                    TaskExample(text="3 + 7 = ", correct_answer="10", points=1),
                    TaskExample(text="6 + 6 = ", correct_answer="12", points=1),
                    TaskExample(text="8 + 3 = ", correct_answer="11", points=1),
                    TaskExample(text="9 + 8 = ", correct_answer="17", points=1),
                    TaskExample(text="7 + 5 = ", correct_answer="12", points=1),
                ]
            )
            task23 = Task(
                title="№2",
                text="",
                type="examples",
                order=2,
                block=block3,
                examples=[
                    TaskExample(text="19 - 2 = ", correct_answer="17", points=1),
                    TaskExample(text="15 + 6 = ", correct_answer="21", points=1),
                    TaskExample(text="12 - 7 = ", correct_answer="5", points=1),
                    TaskExample(text="13 + 8 = ", correct_answer="21", points=1),
                    TaskExample(text="11 + 6 = ", correct_answer="17", points=1),
                    TaskExample(text="14 - 8 = ", correct_answer="6", points=1),
                    TaskExample(text="8 + 11 = ", correct_answer="19", points=1),
                    TaskExample(text="17 - 9 = ", correct_answer="8", points=1),
                    TaskExample(text="14 + 8 = ", correct_answer="22", points=1),
                    TaskExample(text="15 - 6 = ", correct_answer="9", points=1),
                    TaskExample(text="18 - 9 = ", correct_answer="9", points=1),
                    TaskExample(text="12 + 7 = ", correct_answer="19", points=1),
                ]
            )
            task24 = Task(
                title="№3",
                text="",
                type="examples",
                order=3,
                block=block3,
                examples=[ # 12+16=28  24+16=40  13+48=61  33+22=55  47+11=58   23+16=39  34+26=60  47+25=72  45+32=77  36+22=58  63+21=84  48+29=77 
                    TaskExample(text="12 + 16 = ", correct_answer="28", points=1),
                    TaskExample(text="24 + 16 = ", correct_answer="40", points=1),
                    TaskExample(text="13 + 48 = ", correct_answer="61", points=1),
                    TaskExample(text="33 + 22 = ", correct_answer="55", points=1),
                    TaskExample(text="47 + 11 = ", correct_answer="58", points=1),
                    TaskExample(text="23 + 16 = ", correct_answer="39", points=1),
                    TaskExample(text="34 + 26 = ", correct_answer="60", points=1),
                    TaskExample(text="47 + 25 = ", correct_answer="72", points=1),
                    TaskExample(text="45 + 32 = ", correct_answer="77", points=1),
                    TaskExample(text="36 + 22 = ", correct_answer="58", points=1),
                    TaskExample(text="63 + 21 = ", correct_answer="84", points=1),
                    TaskExample(text="48 + 29 = ", correct_answer="77", points=1),
                ]
            )
            task25 = Task(
                title="№4",
                text="",
                type="examples",
                order=4,
                block=block3,
                examples=[
                    TaskExample(text="36 + 56 = ", correct_answer="92", points=1),
                    TaskExample(text="87 - 78 = ", correct_answer="9", points=1),
                    TaskExample(text="79 - 53 = ", correct_answer="26", points=1),
                    TaskExample(text="71 + 25 = ", correct_answer="96", points=1),
                    TaskExample(text="72 - 18 = ", correct_answer="54", points=1),
                    TaskExample(text="31 + 54 = ", correct_answer="85", points=1),
                    TaskExample(text="35 - 18 = ", correct_answer="17", points=1),
                    TaskExample(text="48 - 19 = ", correct_answer="29", points=1),
                    TaskExample(text="34 + 26 = ", correct_answer="60", points=1),
                    TaskExample(text="24 + 37 = ", correct_answer="61", points=1),
                    TaskExample(text="20 + 62 = ", correct_answer="82", points=1),
                    TaskExample(text="73 - 46 = ", correct_answer="27", points=1),
                ]
            )

            task26 = Task(
                title="№5",
                text="",
                type="examples",
                order=5,
                block=block3,
                examples=[
                    TaskExample(text="11 + 5 - 3 + 15 - 9 - 2 + 23 - 4 - 7 + 17 - 14 = ", correct_answer="32", points=15),
                ]
            )

            task27 = Task(
                title="№6",
                text="",
                type="examples",
                order=6,
                block=block3,
                examples=[
                    TaskExample(text="23 + 35 - 46 + 72 - 16 - 31 - 9 + 28 + 37 - 62 + 49 = ", correct_answer="80", points=17),
                ]
            )

            db.session.add_all([tour, block3, block1, block2, task1, task2, task3, task4, task5, task6, task7, task8, task9, task10, task11, task12, task13, task14, task15, task16, task17, task18, task19, task20, task21, task22, task23, task24, task25, task26, task27])
            db.session.commit()
        elif i <= 4:
            block1 = TaskBlock(name="Задачи", order=2, max_duration=2100, tournament=tour, image_url="alice2.png")
            task1 = Task(
                title="№1",
                order=1,
                text="Два одинаковых числа сложили, и получилось двузначное число, записанное одинаковыми цифрами. Чему равно получившиеся число, если оно самое маленькое из возможных?",
                correct_answer="22",
                block=block1, 
                points=2
            )
            task2 = Task(
                title="№2",
                order=2,
                text="Из максимального двузначного числа, состоящего из разных цифр, вычли минимальное двузначное число, состоящее из одинаковых цифр, что получилось?",
                correct_answer="87",
                block=block1, 
                points=4
            )
            task3 = Task(
                title="№3",
                order=3,
                text="Миша купил 2 линейки и карандаш и заплатил 17 рублей, а Паша купил карандаш и 2 ручки и заплатил 26 рублей. Сколько стоит 2 линейки, 2 карандаша и 2 ручки?",
                correct_answer="43",
                block=block1, 
                points=2
            )
            task4 = Task(
                title="№4",
                order=4,
                text="Миша купил 3 линейки и карандаш и заплатил 18 рублей, а Паша купил 2 карандаша и 3 ручки и заплатил 24 рублей. Сколько стоит 1 линейка, 1 карандаш и 1 ручка?",
                correct_answer="14",
                block=block1, 
                points=4
            )
            task5 = Task(
                title="№5",
                order=5,
                text="В поход ходил класс 3Б, где 27 учеников, и класс 4А, где 24 ученика. Мальчиков было на 5 больше, чем девочек. Сколько девочек ходило в поход?",
                correct_answer="23",
                block=block1, 
                points=4
            )
            task6 = Task(
                title="№6",
                order=6,
                text="У Кати столько же денег, сколько у Маши. У Паши больше, чем у Кати на 2 рубля, а у Миши на 3 рубля меньше, чем у Маши. Сколько денег у Паши, если у Миши 1 рубль?",
                correct_answer="6",
                block=block1, 
                points=3
            )
            task7 = Task(
                title="№7",
                order=7,
                text="У Маши и Саши вместе скрепышей на 36 штук больше, чем у Бори, а у Бори и Маши вместе на 10 меньше, чем у Саши. Сколько скрепышей у Маши?",
                correct_answer="13",
                block=block1, 
                points=4
            )
            task8 = Task(
                title="№8",
                order=8,
                text="Маша заработала 3 пятерки, ее подруга Катя на 2 пятерки больше, а Миша на 4 пятерки меньше чем Катя и Маша вместе. Сколько пятерок у Маши?",
                correct_answer="3",
                block=block1, 
                points=2
            )
            task9 = Task(
                title="№9",
                order=9,
                text="Если Маша отдаст Злате три ручки, то у них будет поровну ручек. Если Злата отдаст Даше 2 ручки, то у них будет ручек поровну. Сколько ручек у Маши если всего ручек у них 17 штук?",
                correct_answer="11",
                block=block1, 
                points=4
            )
            task10 = Task(
                title="№10",
                order=10,
                text="На сколько изменится сумма, если первое слагаемое увеличится на 5, а второе слагаемое уменьшится на 3? Ввести только число, например 10",
                correct_answer="2",
                block=block1, 
                points=2
            )
            task11 = Task(
                title="№11",
                order=11,
                text="На сколько изменилось первое слагаемое, если второе слагаемое увеличилось на 35, а сумма увеличилась на 14? Ввести только число, например 10",
                correct_answer="21",
                block=block1, 
                points=4
            )
            task12 = Task(
                title="№12",
                order=12,
                text="Елка весит 2кг и еще половину елки. Сколько весит елка с игрушками, если игрушки отдельно весят 1 кг?",
                correct_answer="5",
                block=block1, 
                points=2
            )

            block2 = TaskBlock(name="Геометрия", order=3, max_duration=2100, tournament=tour, image_url="alice3.png")
            task13 = Task(
                title="№1",
                order=1,
                text="Большой куб состоит из 27 маленьких белых кубиков. Из них 4 белых кубика заменили на 4 черных кубика, так чтобы на каждой грани было видно одинаковое количество черных квадратов. Какое максимальное количество черных квадратов на одной грани?",
                correct_answer="2",
                block=block2, 
                points=4
            )
            task14 = Task(
                title="№2",
                order=2,
                text="Какая наименьшая и наибольшая площадь может быть у прямоугольника с целыми сторонами, если его периметр равен 20? Ввести два числа через пробел, например, 1 100",
                correct_answer="9 25",
                block=block2, 
                points=4
            )
            task15 = Task(
                title="№3",
                order=3,
                text="Сколько треугольников на картинке?",
                correct_answer="35",
                image_url="task7.png",
                block=block2, 
                points=4
            )
            task16 = Task(
                title="№4",
                order=4,
                text="Красный большой деревянный куб разрезали на 125 маленьких. Сколько получилось кубиков, не окрашенных в красный цвет?",
                correct_answer="27",
                block=block2, 
                points=3
            )
            task17 = Task(
                title="№5",
                order=5,
                text="Из каких пентамино собрана фигура? В ответе указать номера пентамино в порядке возрастания без пробела. Например, если номера 11 и 12, то записать 1112.",
                correct_answer="2612",
                image_url='task8.png',
                block=block2, 
                points=4
            )
            task18 = Task(
                title="№6",
                order=6,
                text="Из каких пентамино собрана фигура? В ответе указать номера пентамино в порядке возрастания без пробела. Например, если номера 11 и 12, то записать 1112.",
                correct_answer="1378",
                image_url='task9.png',
                block=block2, 
                points=4
            )
            task19 = Task(
                title="№7",
                order=7,
                text="Из некоторых наборов фигур (снизу) собрали картинки (сверху). Какие наборы остались не использованы? В ответе ввести числа в порядке возрастания без пробела, например 910.",
                correct_answer="35",
                image_url='task4.png',
                block=block2, 
                points=3
            )
            task20 = Task(
                title="№8",
                order=8,
                text="Периметр квадрата равен 36см. Квадрат разрезали на два разных прямоугольника, после этого посчитали получившиеся периметры и сложили их. Чему равна сумма периметров двух прямоугольников?",
                correct_answer="54",
                block=block2, 
                points=4
            )
            task21 = Task(
                title="№9",
                order=9,
                text="Периметр прямоугольника равен 24см, чему равна длина прямоугольника, если известно, что она на 2см длиннее ширины прямоугольника?",
                correct_answer="7",
                block=block2, 
                points=4
            )

            block3 = TaskBlock(name="Примеры", order=1, max_duration=600, tournament=tour, image_url="alice1.png")
            task22 = Task(
                title="№1",
                text="",
                type="examples",
                order=1,
                block=block3,
                examples=[
                    TaskExample(text="36 + 56 = ", correct_answer="92", points=1),
                    TaskExample(text="87 - 78 = ", correct_answer="9", points=1),
                    TaskExample(text="79 - 53 = ", correct_answer="26", points=1),
                    TaskExample(text="71 + 25 = ", correct_answer="96", points=1),
                    TaskExample(text="72 - 18 = ", correct_answer="54", points=1),
                    TaskExample(text="31 + 54 = ", correct_answer="85", points=1),
                    TaskExample(text="35 - 18 = ", correct_answer="17", points=1),
                    TaskExample(text="48 - 19 = ", correct_answer="29", points=1),
                    TaskExample(text="34 + 26 = ", correct_answer="60", points=1),
                    TaskExample(text="24 + 37 = ", correct_answer="61", points=1),
                    TaskExample(text="20 + 62 = ", correct_answer="82", points=1),
                    TaskExample(text="73 - 46 = ", correct_answer="27", points=1),
                ]
            )
            task23 = Task(
                title="№2",
                text="",
                type="examples",
                order=2,
                block=block3,
                examples=[
                    TaskExample(text="8 * 9 = ", correct_answer="72", points=1),
                    TaskExample(text="6 * 6 = ", correct_answer="36", points=1),
                    TaskExample(text="45 : 5 = ", correct_answer="9", points=1),
                    TaskExample(text="7 * 8 = ", correct_answer="56", points=1),
                    TaskExample(text="8 * 6 = ", correct_answer="48", points=1),
                    TaskExample(text="9 * 7 = ", correct_answer="63", points=1),
                    TaskExample(text="11 * 3 = ", correct_answer="33", points=1),
                    TaskExample(text="49 : 7 = ", correct_answer="7", points=1),
                    TaskExample(text="81 : 9 = ", correct_answer="9", points=1),
                    TaskExample(text="9 * 4 = ", correct_answer="36", points=1),
                    TaskExample(text="14 * 3 = ", correct_answer="42", points=1),
                    TaskExample(text="48 : 12 = ", correct_answer="4", points=1),
                ]
            )
            task24 = Task(
                title="№3",
                text="",
                type="examples",
                order=3,
                block=block3,
                examples=[ # 150/3=50  24*3=72  63/3=21  18*8=144  75/25=3   13*5=65  144/12=12  25*8=200  72*3=216  153/3=51  21*8=168  11*15=165 
                    TaskExample(text="150 : 3 = ", correct_answer="50", points=1),
                    TaskExample(text="24 * 3 = ", correct_answer="72", points=1),
                    TaskExample(text="63 : 3 = ", correct_answer="21", points=1),
                    TaskExample(text="18 * 8 = ", correct_answer="144", points=1),
                    TaskExample(text="75 : 25 = ", correct_answer="3", points=1),
                    TaskExample(text="13 * 5 = ", correct_answer="65", points=1),
                    TaskExample(text="144 : 12 = ", correct_answer="12", points=1),
                    TaskExample(text="25 * 8 = ", correct_answer="200", points=1),
                    TaskExample(text="72 * 3 = ", correct_answer="216", points=1),
                    TaskExample(text="153 : 3 = ", correct_answer="51", points=1),
                    TaskExample(text="21 * 8 = ", correct_answer="168", points=1),
                    TaskExample(text="11 * 15 = ", correct_answer="165", points=1),
                ]
            )
            task25 = Task(
                title="№4",
                text="",
                type="examples",
                order=4,
                block=block3,
                examples=[
                    TaskExample(text="729 + 27 = ", correct_answer="756", points=1),
                    TaskExample(text="540 - 477 = ", correct_answer="63", points=1),
                    TaskExample(text="321 + 264 = ", correct_answer="585", points=1),
                    TaskExample(text="485 - 308 = ", correct_answer="177", points=1),
                    TaskExample(text="878 - 296 = ", correct_answer="582", points=1),
                    TaskExample(text="638 - 202 = ", correct_answer="436", points=1),
                    TaskExample(text="355 - 84 = ", correct_answer="271", points=1),
                    TaskExample(text="942 - 118 = ", correct_answer="824", points=1),
                    TaskExample(text="463 - 338 = ", correct_answer="125", points=1),
                    TaskExample(text="338 + 463 = ", correct_answer="801", points=1),
                    TaskExample(text="293 + 469 = ", correct_answer="762", points=1),
                    TaskExample(text="258 + 399 = ", correct_answer="657", points=1),
                ]
            )

            task26 = Task(
                title="№5",
                text="",
                type="examples",
                order=5,
                block=block3,
                examples=[
                    TaskExample(text="3 * 6 * 4 : 9 * 5 * 2 : 20 * 24 : 12 : 8 * 10 = ", correct_answer="10", points=15),
                ]
            )

            task27 = Task(
                title="№6",
                text="",
                type="examples",
                order=6,
                block=block3,
                examples=[
                    TaskExample(text="2 * 8 * 3 + 2 * 5 * 12 : 60 - 25 * 4 * 3 : 6 + 14 : 7 * (239 - 144) = ", correct_answer="190", points=17),
                ]
            )

            db.session.add_all([tour, block3, block1, block2, task1, task2, task3, task4, task5, task6, task7, task8, task9, task10, task11, task12, task13, task14, task15, task16, task17, task18, task19, task20, task21, task22, task23, task24, task25, task26, task27])
            db.session.commit()
        else:
            block1 = TaskBlock(name="Задачи", order=2, max_duration=2100, tournament=tour, image_url="alice2.png")
            task1 = Task(
                title="№1",
                order=1,
                text="Из максимального двузначного числа, состоящего из разных цифр, вычли минимальное двузначное число, состоящее из одинаковых цифр, что получилось?",
                correct_answer="87",
                block=block1, 
                points=2
            )
            task2 = Task(
                title="№2",
                order=2,
                text="Максимальное двузначное число, состоящее из одинаковых цифр, умножили на минимальное двузначное число, состоящее из разных положительных цифр, что получилось?",
                correct_answer="1188",
                block=block1, 
                points=3
            )
            task3 = Task(
                title="№3",
                order=3,
                text="Миша купил 3 линейки и карандаш и заплатил 18 рублей, а Паша купил 2 карандаша и 3 ручки и заплатил 24 рублей. Сколько стоит 1 линейка, 1 карандаш и 1 ручка?",
                correct_answer="14",
                block=block1, 
                points=2
            )
            task4 = Task(
                title="№4",
                order=4,
                text="Миша купил 2 линейки и карандаш и заплатил 15 рублей, а Паша купил 2 карандаша, 3 ручки и 1 резинку и заплатил 20 рублей. Даша купила линейку, карандаш и ручку и заплатила 18 рублей. Сколько стоит 1 линейка, 2 карандаша и 2 ручки и резинка?",
                correct_answer="17",
                block=block1, 
                points=3
            )
            task5 = Task(
                title="№5",
                order=5,
                text="В поход ходил класс 3Б, где 27 учеников, и класс 4А, где 24 ученика. Мальчиков было на 5 больше, чем девочек. Сколько девочек ходило в поход?",
                correct_answer="23",
                block=block1, 
                points=2
            )
            task6 = Task(
                title="№6",
                order=6,
                text="У Кати столько же денег, сколько у Маши. У Паши больше, чем у Кати на 2 рубля, а у Миши на 3 рубля меньше, чем у Маши. Сколько всего у ребят, если у Миши 7 рублей?",
                correct_answer="39",
                block=block1, 
                points=3
            )
            task7 = Task(
                title="№7",
                order=7,
                text="У Маши и Саши вместе скрепышей на 36 штук больше, чем у Бори, а у Бори и Маши вместе на 10 меньше, чем у Саши. Сколько скрепышей у Маши?",
                correct_answer="13",
                block=block1, 
                points=2
            )
            task8 = Task(
                title="№8",
                order=8,
                text="У Маши есть 20 рублей. Миша предложил ей купить маленький тортик, но Маша возмутилась: \"Вот если бы у меня было в два раза больше рублей, чем есть, да еще столько же сколько получилось, да еще половина того, что есть, тогда я бы могла купить тортик\". Сколько денег не хватает Маше на тортик?",
                correct_answer="70", # TODO: уточнить
                block=block1, 
                points=3
            )
            task9 = Task(
                title="№9",
                order=9,
                text="Если Маша отдаст Злате три ручки, то у них будет поровну ручек. Если Злата отдаст Даше 2 ручки, то у них будет ручек поровну. Сколько ручек у Маши если всего ручек у них 17 штук?",
                correct_answer="11",
                block=block1, 
                points=2
            )
            task10 = Task(
                title="№10",
                order=10,
                text="На сколько изменилось первое слагаемое, если второе слагаемое увеличилось на 35, а сумма увеличилась на 14? Ввести только число, например 10",
                correct_answer="21",
                block=block1, 
                points=2
            )
            task11 = Task(
                title="№11",
                order=11,
                text="На сколько изменится разность если уменьшаемое увеличится на 13, а вычитаемое уменьшится на 33? Ввести только число, например 10",
                correct_answer="46",
                block=block1, 
                points=3
            )
            task12 = Task(
                title="№12",
                order=12,
                text="Миша и Паша участвовали в соревнованиях по бегу. У Миши скорость 3 м/с и у Паши 11 км/ч. Кто бежит быстрее?",
                correct_answer="Паша",
                block=block1, 
                points=3
            )

            block2 = TaskBlock(name="Геометрия", order=3, max_duration=2100, tournament=tour, image_url="alice3.png")
            task13 = Task(
                title="№1",
                order=1,
                text="Большой куб состоит из 27 маленьких белых кубиков. Из них 4 белых кубика заменили на 4 черных кубика, так чтобы на каждой грани было видно одинаковое количество черных квадратов. Какое максимальное количество черных квадратов на одной грани?",
                correct_answer="2",
                block=block2, 
                points=2
            )
            task14 = Task(
                title="№2",
                order=2,
                text="Какая наименьшая и наибольшая площадь может быть у прямоугольника с целыми сторонами, если его периметр равен 20? Ввести два числа через пробел, например, 1 100",
                correct_answer="9 25",
                block=block2, 
                points=2
            )
            task15 = Task(
                title="№3",
                order=3,
                text="Сколько треугольников на картинке?",
                correct_answer="35",
                image_url="task7.png",
                block=block2, 
                points=2
            )
            task16 = Task(
                title="№4",
                order=4,
                text="Красный большой деревянный куб разрезали на 125 маленьких. Сколько получилось кубиков, где только 2 грани окрашены в красный цвет?",
                correct_answer="36",
                block=block2, 
                points=3
            )
            task17 = Task(
                title="№5",
                order=5,
                text="Из каких пентамино собрана фигура? В ответе указать номера пентамино в порядке возрастания без пробела. Например, если номера 11 и 12, то записать 1112.",
                correct_answer="2612",
                image_url='task8.png',
                block=block2, 
                points=2
            )
            task18 = Task(
                title="№6",
                order=6,
                text="Из каких пентамино собрана фигура? В ответе указать номера пентамино в порядке возрастания без пробела. Например, если номера 11 и 12, то записать 1112.",
                correct_answer="1378",
                image_url='task9.png',
                block=block2, 
                points=3
            )
            task19 = Task(
                title="№7",
                order=7,
                text="Из некоторых наборов фигур (снизу) собрали картинки (сверху). Какие наборы остались не использованы? В ответе ввести числа в порядке возрастания без пробела, например 910.",
                correct_answer="35",
                image_url='task4.png',
                block=block2, 
                points=3
            )
            task20 = Task(
                title="№8",
                order=8,
                text="Периметр квадрата равен 36см. Квадрат разрезали на два разных прямоугольника, после этого посчитали получившиеся периметры и сложили их. Чему равна сумма периметров двух прямоугольников?",
                correct_answer="54",
                block=block2, 
                points=2
            )
            task21 = Task(
                title="№9",
                order=9,
                text="Периметр прямоугольника равен 24см, чему равна длина прямоугольника, если известно, что она на 2см длиннее ширины прямоугольника?",
                correct_answer="7",
                block=block2, 
                points=2
            )

            block3 = TaskBlock(name="Примеры", order=1, max_duration=600, tournament=tour, image_url="alice1.png")
            task22 = Task(
                title="№1",
                text="",
                type="examples",
                order=1,
                block=block3,
                examples=[
                    TaskExample(text="36 + 56 = ", correct_answer="92", points=1),
                    TaskExample(text="87 - 78 = ", correct_answer="9", points=1),
                    TaskExample(text="79 - 53 = ", correct_answer="26", points=1),
                    TaskExample(text="71 + 25 = ", correct_answer="96", points=1),
                    TaskExample(text="72 - 18 = ", correct_answer="54", points=1),
                    TaskExample(text="31 + 54 = ", correct_answer="85", points=1),
                    TaskExample(text="35 - 18 = ", correct_answer="17", points=1),
                    TaskExample(text="48 - 19 = ", correct_answer="29", points=1),
                    TaskExample(text="34 + 26 = ", correct_answer="60", points=1),
                    TaskExample(text="24 + 37 = ", correct_answer="61", points=1),
                    TaskExample(text="20 + 62 = ", correct_answer="82", points=1),
                    TaskExample(text="73 - 46 = ", correct_answer="27", points=1),
                ]
            )
            task23 = Task(
                title="№2",
                text="",
                type="examples",
                order=2,
                block=block3,
                examples=[
                    TaskExample(text="150 : 3 = ", correct_answer="50", points=1),
                    TaskExample(text="24 * 3 = ", correct_answer="72", points=1),
                    TaskExample(text="63 : 3 = ", correct_answer="21", points=1),
                    TaskExample(text="18 * 8 = ", correct_answer="144", points=1),
                    TaskExample(text="75 : 25 = ", correct_answer="3", points=1),
                    TaskExample(text="13 * 5 = ", correct_answer="65", points=1),
                    TaskExample(text="144 : 12 = ", correct_answer="12", points=1),
                    TaskExample(text="25 * 8 = ", correct_answer="200", points=1),
                    TaskExample(text="72 * 3 = ", correct_answer="216", points=1),
                    TaskExample(text="153 : 3 = ", correct_answer="51", points=1),
                    TaskExample(text="21 * 8 = ", correct_answer="168", points=1),
                    TaskExample(text="11 * 15 = ", correct_answer="165", points=1),
                ]
            )
            task24 = Task(
                title="№3",
                text="",
                type="examples",
                order=3,
                block=block3,
                examples=[
                    TaskExample(text="729 + 27 = ", correct_answer="756", points=1),
                    TaskExample(text="540 - 477 = ", correct_answer="63", points=1),
                    TaskExample(text="321 + 264 = ", correct_answer="585", points=1),
                    TaskExample(text="485 - 308 = ", correct_answer="177", points=1),
                    TaskExample(text="878 - 296 = ", correct_answer="582", points=1),
                    TaskExample(text="638 - 202 = ", correct_answer="436", points=1),
                    TaskExample(text="355 - 84 = ", correct_answer="271", points=1),
                    TaskExample(text="942 - 118 = ", correct_answer="824", points=1),
                    TaskExample(text="463 - 338 = ", correct_answer="125", points=1),
                    TaskExample(text="338 + 463 = ", correct_answer="801", points=1),
                    TaskExample(text="293 + 469 = ", correct_answer="762", points=1),
                    TaskExample(text="258 + 399 = ", correct_answer="657", points=1),
                ]
            )
            task25 = Task(
                title="№4",
                text="",
                type="examples",
                order=4,
                block=block3,
                examples=[
                    TaskExample(text="2 ^ 8 = ", correct_answer="256", points=1),
                    TaskExample(text="6! = ", correct_answer="720", points=1),
                    TaskExample(text="3! = ", correct_answer="6", points=1),
                    TaskExample(text="5 ^ 3 = ", correct_answer="125", points=1),
                    TaskExample(text="15 * 15 = ", correct_answer="225", points=1),
                    TaskExample(text="25 * 99 = ", correct_answer="2475", points=1),
                    TaskExample(text="24 * 50 = ", correct_answer="1200", points=1),
                    TaskExample(text="363 : 11 = ", correct_answer="33", points=1),
                    TaskExample(text="34 * 19 = ", correct_answer="646", points=1),
                    TaskExample(text="380 : 19 = ", correct_answer="20", points=1),
                    TaskExample(text="21 * 78 = ", correct_answer="1638", points=1),
                    TaskExample(text="345 : 15 = ", correct_answer="23", points=1),
                ]
            )

            task26 = Task(
                title="№5",
                text="",
                type="examples",
                order=5,
                block=block3,
                examples=[
                    TaskExample(text="2 * 8 * 3 + 2 * 5 * 12 : 60 - 25 * 4 * 3 : 6 + 14 : 7 * (239 - 144) = ", correct_answer="190", points=15),
                ]
            )

            task27 = Task(
                title="№6",
                text="",
                type="examples",
                order=6,
                block=block3,
                examples=[
                    TaskExample(text="3 * (3 + 510 : 17) + 2 * (178 + 165 - 456 : 3) = ", correct_answer="481", points=17),
                ]
            )

            db.session.add_all([tour, block3, block1, block2, task1, task2, task3, task4, task5, task6, task7, task8, task9, task10, task11, task12, task13, task14, task15, task16, task17, task18, task19, task20, task21, task22, task23, task24, task25, task26, task27])
            db.session.commit()