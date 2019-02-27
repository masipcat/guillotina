from guillotina import configure
from guillotina import schema
from guillotina.behaviors.dublincore import IDublinCore
from guillotina.behaviors.instance import AnnotationBehavior
from guillotina.behaviors.properties import ContextProperty
from guillotina.component import get_utility
from guillotina.content import create_content
from guillotina.content import create_content_in_container
from guillotina.content import Folder
from guillotina.content import Item
from guillotina.content import load_cached_schema
from guillotina.exceptions import NoPermissionToAdd
from guillotina.exceptions import NotAllowedContentType
from guillotina.interfaces import IApplication
from guillotina.interfaces import IResource
from guillotina.interfaces import IItem
from guillotina.interfaces.types import IConstrainTypes
from guillotina.schema import Dict
from guillotina.schema import TextLine
from guillotina.tests import utils
from zope.interface import Interface

import json
import pickle
import pytest


class IComment(Interface):

    msg = schema.TextLine(required=True)


class IComments(Interface):

    comments = schema.List(value_type=schema.Object(schema=IComment), required=False)
    json_comments = schema.List(value_type=schema.JSONField(), required=False)


class ICommentsMarker(Interface):
    """
    Marker interface for content with Comments
    """


@configure.behavior(
    title="Comments",
    provides=IComments,
    marker=ICommentsMarker,
    for_=IResource,
)
class CommentsBehavior(AnnotationBehavior):

    # This line fixes the problem
    # __local__properties__ = ("comments", "json_comments")

    comments = ContextProperty("comments", [])
    json_comments = ContextProperty("json_comments", [])


class ICustomContentType(IItem):

    images = Dict(
        key_type=TextLine(),
        value_type=TextLine(),
        required=False,
        defaultFactory=dict
    )


@configure.contenttype(
    type_name="CustomContentType",
    schema=ICustomContentType,
    behaviors=[IComments.__identifier__, IDublinCore.__identifier__],
)
class CustomContentType(Item):
    pass


@pytest.mark.usefixtures("dummy_request")
class TestContent:
    async def test_not_allowed_to_create_content(self, dummy_request):
        self.request = dummy_request

        container = await create_content(
            'Container',
            id='guillotina',
            title='Guillotina')
        container.__name__ = 'guillotina'

        with pytest.raises(NoPermissionToAdd):
            # not logged in, can't create
            await create_content_in_container(container, 'Item', id_='foobar')

    async def test_allowed_to_create_content(self, dummy_request):
        self.request = dummy_request
        utils.login(self.request)

        container = await create_content(
            'Container',
            id='guillotina',
            title='Guillotina')
        container.__name__ = 'guillotina'
        utils._p_register(container)

        await create_content_in_container(container, 'Item', id_='foobar')

    async def test_allowed_types(self, dummy_request):
        self.request = dummy_request
        utils.login(self.request)

        container = await create_content(
            'Container',
            id='guillotina',
            title='Guillotina')
        container.__name__ = 'guillotina'
        utils._p_register(container)

        import guillotina.tests
        configure.register_configuration(Folder, dict(
            type_name="TestType",
            allowed_types=['Item'],
            module=guillotina.tests  # for registration initialization
        ), 'contenttype')
        root = get_utility(IApplication, name='root')

        configure.load_configuration(
            root.app.config, 'guillotina.tests', 'contenttype')
        root.app.config.execute_actions()
        load_cached_schema()

        obj = await create_content_in_container(container, 'TestType', 'foobar')

        constrains = IConstrainTypes(obj, None)
        assert constrains.get_allowed_types() == ['Item']
        assert constrains.is_type_allowed('Item')

        with pytest.raises(NotAllowedContentType):
            await create_content_in_container(obj, 'TestType', 'foobar')
        await create_content_in_container(obj, 'Item', 'foobar')

    async def test_creator_used_from_content_creation(self, dummy_request):
        self.request = dummy_request
        utils.login(self.request)

        container = await create_content(
            'Container',
            id='guillotina',
            title='Guillotina')
        container.__name__ = 'guillotina'
        utils._p_register(container)

        import guillotina.tests
        configure.register_configuration(Folder, dict(
            type_name="TestType2",
            behaviors=[],
            module=guillotina.tests  # for registration initialization
        ), 'contenttype')
        root = get_utility(IApplication, name='root')

        configure.load_configuration(
            root.app.config, 'guillotina.tests', 'contenttype')
        root.app.config.execute_actions()
        load_cached_schema()

        obj = await create_content_in_container(
            container, 'TestType2', 'foobar',
            creators=('root',), contributors=('root',))

        assert obj.creators == ('root',)
        assert obj.contributors == ('root',)

        behavior = IDublinCore(obj)
        assert behavior.creators == ('root',)
        assert behavior.contributors == ('root',)


def test_base_object():
    testing = {
        '__parent__': '_BaseObject__parent',
        '__of__': '_BaseObject__of',
        '__name__': '_BaseObject__name',
        '__gannotations__': '_BaseObject__annotations',
        '__immutable_cache__': '_BaseObject__immutable_cache',
        '__new_marker__': '_BaseObject__new_marker',
        '_p_jar': '_BaseObject__jar',
        '_p_oid': '_BaseObject__oid',
        '_p_serial': '_BaseObject__serial'
    }
    for name, attr in testing.items():
        item = Item()
        setattr(item, name, 'foobar')
        assert name not in item.__dict__
        assert attr not in item.__dict__
        pickled = pickle.dumps(item, protocol=pickle.HIGHEST_PROTOCOL)
        new_item = pickle.loads(pickled)
        assert getattr(new_item, name) != 'foobar'
        assert name not in item.__dict__
        assert attr not in item.__dict__


async def test_getattr_set_default(container_requester):
    custom_content = await create_content('CustomContentType')

    images1 = custom_content.images
    images2 = custom_content.images

    assert isinstance(images1, dict)

    # Assert that obj.__getattr__() returns always same instance of default value
    # for empty fields
    assert id(images1) == id(images2)


async def test_create_item_with_behavior(container_requester):
    async with container_requester as requester:
        _, status = await requester(
            'POST', '/db/guillotina', data=
            json.dumps({
                '@type': 'CustomContentType',
                'id': 'foobar',
                'images': {
                    'a': 'b'
                },
                IComments.__identifier__: {
                    'comments': [{'msg': 'hola'}],
                    'json_comments': [{'msg': 'adeu Andreu'}]
                },
                IDublinCore.__identifier__: {
                    'creators': ('root',),
                    'contributors': ('root',),
                    'publisher': '@masipcat',
                }
            })
        )
        assert status == 201

        resp, status = await requester('GET', '/db/guillotina/foobar')
        assert status == 200

        assert resp['images'] == {'a': 'b'}
        assert resp[IDublinCore.__identifier__]['creators'] == ['root']
        assert resp[IDublinCore.__identifier__]['contributors'] == ['root']
        assert resp[IDublinCore.__identifier__]['publisher'] == '@masipcat'

        # Doesn't work
        assert resp[IComments.__identifier__]['json_comments'] == [{'msg': 'adeu Andreu'}]
        assert resp[IComments.__identifier__]['comments'] ==  [{'msg': 'hola'}]
