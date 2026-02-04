import unittest
import typing
from unittest.mock import patch
from dataclasses import field, InitVar
from pydantic_mini import BaseModel, MiniAnnotated, Attrib, preformat, validator
from pydantic_mini.exceptions import ValidationError


class TestBase(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        class MyModel(BaseModel):
            name: str
            age: int

        class DataClassField(BaseModel):
            school = field(default="knust")
            value = field(default_factory=lambda: 1)

        class AnnotatedDataClass(BaseModel):
            email: MiniAnnotated[
                str, Attrib(pattern=r"^[^@]+@[^@]+\.[^@]+$", max_length=13)  # noqa:
            ]
            value: MiniAnnotated[int, Attrib(gt=4, lt=20, default=5)]

        class UsingOptionalDataClass(BaseModel):
            value: typing.Optional[int]
            name: MiniAnnotated[typing.Optional[str], Attrib(max_length=20)]

        class DisabledAllValidationClass(BaseModel):
            email: MiniAnnotated[
                str, Attrib(pattern=r"^[^@]+@[^@]+\.[^@]+$", max_length=13)  # noqa:
            ]
            value: MiniAnnotated[int, Attrib(gt=4, lt=20, default=5)]

            class Config:
                disable_all_validation = True

        class DisabledTypeCheckValidationClass(BaseModel):
            email: MiniAnnotated[
                str, Attrib(pattern=r"^[^@]+@[^@]+\.[^@]+$", max_length=13)  # noqa:
            ]
            value: MiniAnnotated[int, Attrib(gt=4, lt=20, default=5)]

            class Config:
                disable_typecheck = True

        cls.MyModel = MyModel
        cls.DataClassField = DataClassField
        cls.AnnotatedDataClass = AnnotatedDataClass
        cls.UsingOptionalDataClass = UsingOptionalDataClass
        cls.DisabledAllValidationClass = DisabledAllValidationClass
        cls.DisabledTypeCheckValidationClass = DisabledTypeCheckValidationClass

    def test_simple_annotated_model(self):
        instance = self.MyModel(name="test", age=10)
        self.assertEqual(instance.name, "test")
        self.assertEqual(instance.age, 10)

        with self.assertRaises(TypeError):
            self.MyModel(name=12, age="hello")

    def test_dataclass_field(self):
        instance = self.DataClassField()
        self.assertEqual(instance.school, "knust")
        self.assertEqual(instance.value, 1)

        # validate detected type from default
        with self.assertRaises(TypeError):
            self.DataClassField(school=23, value="hello")

    def test_mini_annotated_annotation(self):
        instance = self.AnnotatedDataClass(value=10, email="ex@email.com")
        self.assertEqual(instance.email, "ex@email.com")
        self.assertEqual(instance.value, 10)

        with self.assertRaises(ValidationError):
            self.AnnotatedDataClass(value=10, email="ex")

        with self.assertRaises(ValidationError):
            self.AnnotatedDataClass(value=10, email="looooooooong-email@example.com")

    def test_fields_with_or_without_default_values_cause_error(self):
        class Person(BaseModel):
            name: str = "nafiu"
            school: str

        class Person1(BaseModel):
            name: str
            school: str = "knust"

        p1 = Person(school="knust")
        self.assertEqual(p1.name, "nafiu")
        self.assertEqual(p1.school, "knust")

        p2 = Person1(name="nafiu")
        self.assertEqual(p2.name, "nafiu")
        self.assertEqual(p2.school, "knust")

        # validate positional arguments are required
        with self.assertRaises(AttributeError):
            Person(name="nafiu")

        with self.assertRaises(AttributeError):
            Person1(school="knust")

    def test_figured_out_optional_field_from_annotation_has_none_value(self):
        p = self.UsingOptionalDataClass()
        self.assertEqual(p.value, None)
        self.assertEqual(p.name, None)

    def test_model_creation_with_dict(self):
        param = {"name": "nafiu", "age": 12}
        instance = self.MyModel.loads(param, _format="dict")
        self.assertEqual(instance.name, "nafiu")
        self.assertEqual(instance.age, 12)

    def test_model_serialization_with_dict(self):
        instance = self.MyModel(name="nafiu", age=12)
        _dict = instance.dump(_format="dict")
        self.assertIsInstance(_dict, dict)
        self.assertEqual(_dict, {"name": "nafiu", "age": 12})

    def test_multiple_model_creation_with_dict(self):
        params = [
            {"name": "nafiu", "age": 12},
            {"name": "shaibu", "age": 13},
            {"name": "nshaibu", "age": 14},
        ]
        instance = self.MyModel.loads(params, _format="dict")
        self.assertIsInstance(instance, list)
        self.assertEqual(len(instance), len(params))

    def test_inner_model_creation_with_dict_and_list(self):
        class School(BaseModel):
            name: str
            location: str

        class Person(BaseModel):
            name: str
            school: typing.List[School]

        instance = Person(name="nafiu", school=[School("knust", location="kumasi")])
        self.assertIsInstance(instance, Person)
        self.assertEqual(instance.name, "nafiu")
        self.assertEqual(instance.school[0].name, "knust")
        self.assertEqual(instance.school[0].location, "kumasi")

        # convert dict to BaseModel test
        instance1 = Person(
            name="shaibu", school=[{"name": "knust", "location": "kumasi"}]
        )
        self.assertIsInstance(instance1, Person)
        self.assertEqual(instance1.name, "shaibu")
        self.assertEqual(instance1.school[0].name, "knust")
        self.assertEqual(instance1.school[0].location, "kumasi")

        # multiple
        instance2 = Person(
            name="nshaibu",
            school=[
                {"name": "knust", "location": "kumasi"},
                School("legon", location="accra"),
            ],
        )
        self.assertIsInstance(instance2, Person)
        self.assertEqual(instance2.name, "nshaibu")
        self.assertEqual(len(instance2.school), 2)

    def test_inner_model_creation_with_normal_class(self):
        class School:
            def __init__(self, name: str, location: str):
                self.name: str = name
                self.location: str = location

        class Student(BaseModel):
            name: str
            school: School

        student = Student(name="nafiu", school=School("knust", location="kumasi"))
        self.assertIsInstance(student, Student)
        self.assertEqual(student.name, "nafiu")
        self.assertIsInstance(student.school, School)
        self.assertEqual(student.school.name, "knust")
        self.assertEqual(student.school.location, "kumasi")

        # multiple entries
        with self.assertRaises(TypeError):
            Student(name="nafiu", school=[School("knust", location="kumasi")])

        class Person(BaseModel):
            name: str
            school: typing.List[School]

        person = Person(name="nafiu", school=[School("knust", location="kumasi")])
        self.assertIsInstance(person, Person)
        self.assertEqual(person.name, "nafiu")
        self.assertIsInstance(person.school, list)
        self.assertEqual(len(person.school), 1)
        self.assertEqual(person.school[0].name, "knust")
        self.assertEqual(person.school[0].location, "kumasi")

        instance1 = Person(
            name="shaibu",
            school=[
                {"name": "knust", "location": "kumasi"},
                School("legon", location="accra"),
            ],
        )
        self.assertIsInstance(instance1, Person)
        self.assertEqual(instance1.name, "shaibu")
        self.assertIsInstance(instance1.school, list)
        self.assertEqual(len(instance1.school), 2)

    def test_validation_for_all_fields(self):
        class Person(BaseModel):
            name: str
            school_name: str

            @validator(["school_name", "name"])
            def validate(self, value):
                if len(value) > 10:
                    raise ValidationError("Value too long")

        instance = Person(name="nafiu", school_name="knust")
        self.assertEqual(instance.school_name, "knust")
        self.assertEqual(instance.name, "nafiu")

        with self.assertRaises(ValidationError):
            Person(name="loooong-user-name", school_name="knust")

        with self.assertRaises(ValidationError):
            Person(name="nafiu", school_name="loooong-school-name")

    def test_custom_field_validator(self):
        def validate_name(instance, value):
            if len(value) > 10:
                raise ValidationError("Value too long")

        def validate_school_name(instance, value):
            if len(value) > 6:
                raise ValidationError("Value too long")

        class Person(BaseModel):
            name: MiniAnnotated[str, Attrib(validators=[validate_name])]
            school_name: MiniAnnotated[str, Attrib(validators=[validate_school_name])]

        person = Person(name="nafiu", school_name="knust")
        self.assertEqual(person.name, "nafiu")
        self.assertEqual(person.school_name, "knust")

        with self.assertRaises(ValidationError):
            Person(
                name="nafiu",
                school_name="kwame nkrumah university of science and technology",
            )

        with self.assertRaises(ValidationError):
            Person(name="very long user name", school_name="knust")

    def test_validators_model_method(self):
        class Person(BaseModel):
            name: str
            school_name: str

            @validator(["school_name"])
            def validate_school_name(self, value):
                if len(value) > 6:
                    raise ValidationError("Value too long")

            @validator(["name"])
            def validate_name(self, value):
                if len(value) > 10:
                    raise ValidationError("Value too long")

        person = Person(name="nafiu", school_name="knust")
        self.assertEqual(person.name, "nafiu")
        self.assertEqual(person.school_name, "knust")

        with self.assertRaises(ValidationError):
            Person(
                name="nafiu",
                school_name="kwame nkrumah university of science and technology",
            )

        with self.assertRaises(ValidationError):
            Person(name="verrrry looooooooong naaaaame", school_name="knust")

    def test_model_field_method_validators_can_transform_field_value(self):
        class Person(BaseModel):
            name: str
            school_name: str

            @preformat(["school_name"])
            def validate_school_name(self, value):
                return value.upper()

            @preformat(["name"])
            def validate_name(self, value):
                return value.upper()

        person = Person(name="nafiu", school_name="knust")
        self.assertEqual(person.name, "NAFIU")
        self.assertEqual(person.school_name, "KNUST")

    def test_model_custom_field_validators_can_transform_field_value(self):
        def format_school_name(instance, value):
            return value.upper()

        def format_name(instance, value):
            return value.upper()

        class Person(BaseModel):
            name: MiniAnnotated[str, Attrib(pre_formatter=format_name)]
            school_name: MiniAnnotated[str, Attrib(pre_formatter=format_school_name)]

        person = Person(name="nafiu", school_name="knust")
        self.assertEqual(person.name, "NAFIU")
        self.assertEqual(person.school_name, "KNUST")

    def test_attribute_validation(self):
        class Person(BaseModel):
            name: MiniAnnotated[str, Attrib(max_length=10, min_length=2)]
            age: MiniAnnotated[int, Attrib(le=14)]
            number_of_dependents: MiniAnnotated[int, Attrib(default=3, lt=4)]

        with self.assertRaises(ValidationError):
            Person(name="n", age=14)

        with self.assertRaises(ValidationError):
            Person(name="very very loong name", age=14)

        with self.assertRaises(ValidationError):
            p0 = Person(name="nshaibu", age=17)
            self.assertEqual(p0.number_of_dependents, 3)

        with self.assertRaises(ValidationError):
            p1 = Person(name="nafiu", age=15, number_of_dependents=2)
            self.assertEqual(p1.number_of_dependents, 2)

    def test_all_field_validator_method_can_transform_field_value(self):
        class Person(BaseModel):
            name: str
            school_name: str

            @preformat(["school_name", "name"])
            def validate(self, value):
                return value.upper()

        person = Person(name="nafiu", school_name="knust")
        self.assertEqual(person.name, "NAFIU")
        self.assertEqual(person.school_name, "KNUST")

    def test_union_test_annotation_validator_types_in_union(self):
        class Person(BaseModel):
            name: str
            location: typing.Union[int, str]

            class Config:
                strict_mode = True

        person = Person(name="nafiu", location="kumasi")
        self.assertEqual(person.name, "nafiu")
        self.assertEqual(person.location, "kumasi")

        person = Person(name="nafiu", location=12)
        self.assertEqual(person.name, "nafiu")
        self.assertEqual(person.location, 12)

        with self.assertRaises(TypeError):
            Person(name="nafiu", location=Person)

    def test_dataclass_composition_association(self):
        class School(BaseModel):
            name: str
            location: str

        class Person(BaseModel):
            name: str
            school: School

        person = Person(name="nafiu", school=School(name="knust", location="kumasi"))
        self.assertEqual(person.name, "nafiu")
        self.assertEqual(person.school.name, "knust")
        self.assertEqual(person.school.location, "kumasi")

        person1 = Person(name="nafiu", school={"name": "knust", "location": "kumasi"})
        self.assertEqual(person1.name, "nafiu")
        self.assertEqual(person1.school.name, "knust")
        self.assertEqual(person1.school.location, "kumasi")

    def test_normal_class_composition_association(self):
        class School:
            def __init__(self, name: str, location: str):
                self.name = name
                self.location = location

        class Person(BaseModel):
            name: str
            school: School

        person = Person(name="nafiu", school=School(name="knust", location="kumasi"))
        self.assertEqual(person.name, "nafiu")
        self.assertEqual(person.school.name, "knust")
        self.assertEqual(person.school.location, "kumasi")

        person1 = Person(name="nafiu", school={"name": "knust", "location": "kumasi"})
        self.assertEqual(person1.name, "nafiu")
        self.assertEqual(person1.school.name, "knust")
        self.assertEqual(person1.school.location, "kumasi")

    def test_init_model_is_call(self):
        class Person(BaseModel):
            name: str
            school: InitVar[str]

            def __post_init__(self, school):
                self.school = school

        person = Person(name="nafiu", school="knust")
        self.assertEqual(person.name, "nafiu")
        self.assertEqual(person.school, "knust")

        with patch.object(Person, "__post_init__", return_value=None) as mock_init:
            Person(name="nafiu", school="knust")
            mock_init.assert_called_once_with("knust")

    def test_positioning_kwargs_before_positional_arguments_does_not_throw_errors(self):
        class Person(BaseModel):
            name: str = "nafiu"
            school: str

        class Person1(BaseModel):
            name: str
            school: str = "knust"

        class Person2(BaseModel):
            name = "nafiu"
            school: int

        person = Person(school="knust")
        self.assertEqual(person.name, "nafiu")
        self.assertEqual(person.school, "knust")

        person1 = Person1(name="nafiu")
        self.assertEqual(person1.name, "nafiu")
        self.assertEqual(person1.school, "knust")

        person2 = Person2(school=33)
        self.assertEqual(person2.name, "nafiu")
        self.assertEqual(person2.school, 33)

    def test_miniannotated_validate_args(self):
        with self.assertRaises(TypeError):

            class Person(BaseModel):
                name: MiniAnnotated[str, 12, "hello"]

        with self.assertRaises(TypeError):

            class Person(BaseModel):
                name: MiniAnnotated[str, 12]

        with self.assertRaises((ValueError, TypeError)):

            class Person(BaseModel):
                name: MiniAnnotated[typing.Optional, Attrib()]

    def test_type_validation_using_any_annotation(self):
        class Person(BaseModel):
            name: typing.Any
            school: typing.Any

        person = Person(name="nafiu", school="knust")
        self.assertEqual(person.name, "nafiu")
        self.assertEqual(person.school, "knust")

    def test_can_validate_collection_fields(self):
        class Person(BaseModel):
            names: typing.List[str]

        person = Person(names=["a", "b", "c"])
        self.assertEqual(person.names, ["a", "b", "c"])

    def test_overridden_init_and_post_init_raises_permissionerror(self):
        with self.assertRaises(PermissionError):

            class Person(BaseModel):
                names: typing.List[str]

                def __init__(self, names):
                    self.names = names

        # with self.assertRaises(PermissionError):
        #
        #     class Person1(BaseModel):
        #         names: typing.List[str]
        #
        #         def __post_init__(self):
        #             pass

    def test_model_can_be_configured(self):
        class Person(BaseModel):
            name: str
            location: str

            class Config:
                frozen = True

        p = Person(name="nafiu", location="kumasi")
        self.assertEqual(p.name, "nafiu")
        self.assertEqual(p.location, "kumasi")
        self.assertIsInstance(hash(p), int)

        class Person1(BaseModel):
            name: str
            location: str

        p = Person1(name="nafiu", location="kumasi")
        with self.assertRaises(TypeError):
            hash(p)

        class Person2(BaseModel):
            name: str
            location: str

            class Config:
                unsafe_hash = True

        p2 = Person2(name="nafiu", location="kumasi")
        self.assertIsInstance(hash(p2), int)

    def test_disabling_all_validations(self):
        example = self.DisabledAllValidationClass(email="nafiu", value="me")
        self.assertEqual(example.email, "nafiu")
        self.assertEqual(example.value, "me")

    def test_disabling_type_checking(self):
        with self.assertRaises(ValidationError):
            self.DisabledTypeCheckValidationClass(email="nafiu", value="me")

        with self.assertRaises(TypeError):
            self.DisabledTypeCheckValidationClass(email="nafiu@ex.com", value="me")

    def test_coercion_doesnt_work_in_strict_mode(self):
        class Location(BaseModel):
            name: str

        class Person(BaseModel):
            name: str
            location: Location

            class Config:
                strict_mode = True

        with self.assertRaises(TypeError):
            Person.loads(
                {"name": "nafiu", "location": {"name": "kumasi"}}, _format="dict"
            )
