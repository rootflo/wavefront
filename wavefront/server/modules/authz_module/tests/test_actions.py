import pytest

from authz_module import Legacy, define_action, get_action
from authz_module.actions import ActionConflict


@pytest.mark.parametrize(
    'name',
    [
        'agents',
        'agents:create_agent',
        'Agents:CreateAgent',
        'agents:',
        ':Create',
        'a:b:C',
    ],
)
def test_names_follow_service_verb_noun(name):
    with pytest.raises(ValueError):
        define_action(name, legacy=Legacy.ADMIN)


def test_redeclaring_with_the_same_rule_shares_the_action():
    first = define_action('test_actions:GetThing', legacy=Legacy.ADMIN)
    second = define_action(
        'test_actions:GetThing', legacy=Legacy.ADMIN, description='Read a thing'
    )
    assert second.legacy == first.legacy
    assert get_action('test_actions:GetThing').description == 'Read a thing'


def test_redeclaring_with_another_rule_is_refused():
    define_action('test_actions:UpdateThing', legacy=Legacy.ADMIN)
    with pytest.raises(ActionConflict):
        define_action('test_actions:UpdateThing', legacy=Legacy.AUTHENTICATED)


def test_redeclaring_on_another_resource_type_is_refused():
    define_action('test_actions:DeleteThing', legacy=Legacy.ADMIN, resource_type='a')
    with pytest.raises(ActionConflict):
        define_action(
            'test_actions:DeleteThing', legacy=Legacy.ADMIN, resource_type='b'
        )


def test_custom_rules_compare_by_name():
    async def check(*_):
        return True

    define_action('test_actions:RunThing', legacy=Legacy.CUSTOM('mine', check))
    define_action('test_actions:RunThing', legacy=Legacy.CUSTOM('mine', check))


def test_catalog_entry():
    spec = define_action(
        'test_actions:ListThings',
        legacy=Legacy.ADMIN_OR_FLAG('open'),
        resource_type='t',
    )
    assert spec.to_dict() == {
        'action': 'test_actions:ListThings',
        'service': 'test_actions',
        'resource_type': 't',
        'description': '',
        'legacy': 'ADMIN_OR_FLAG(open)',
    }
