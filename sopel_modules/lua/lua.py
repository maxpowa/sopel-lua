# coding=utf-8

from __future__ import unicode_literals, absolute_import, division, print_function

from sopel import module
import os
import lupa
import json


def configure(config):
    pass


def setup(bot):
    pass


class Extras:
    def str(self, obj):
        if not isinstance(obj, str):
            return self.dump_json(obj)
        return '%s' % obj

    def load_json(self, obj):
        return json.loads(obj)

    def dump_json(self, obj):
        return json.dumps(obj)


@module.commands('lua')
def lua_cmd(bot, trigger):
    extras = Extras()
    _allowed_object_attrs = {}
    _allowed_object_attrs[bot] = [
        'say', 
        'reply',
        'db'
    ]
    _allowed_object_attrs[bot.db] = [
        'get_nick_value', 
        'get_channel_value', 
        'get_nick_or_channel_value', 
        'get_preferred_value'
    ]
    _allowed_object_attrs[trigger] = [
        'nick',
        'sender',
        'groups',
        'group',
        'host'
    ]
    _allowed_object_attrs[extras] = ['*']
    

    def _attr_getter(obj, attr_name):
        print('accessing %s.%s' % (obj, attr_name))
        if isinstance(obj, dict):
            return obj.get(attr_name)

        if not isinstance(attr_name, str):
            raise lupa.LuaError("permission denied %r" % attr_name)

        if isinstance(attr_name, str) and (attr_name.startswith("_") and attr_name != '_G'):
            raise lupa.LuaError("permission denied %r" % attr_name)

        if obj not in _allowed_object_attrs:
            raise lupa.LuaError("permission denied %r" % obj)

        if (attr_name not in _allowed_object_attrs[obj] and 
            '*' not in _allowed_object_attrs[obj]):
            raise lupa.LuaError("permission denied %r" % attr_name)

        value = getattr(obj, attr_name)
        return value

    def _attr_setter(obj, attr_name, value):
        if (attr_name == '_G'):
            return setattr(obj, attr_name, value)
        raise lupa.LuaError('permission denied')

    lua = lupa.LuaRuntime(attribute_handlers=(_attr_getter, _attr_setter))
    setup_lua_paths(lua, None)

#    sandbox_script(lua, trigger.group(2), bot, trigger, extras)
    try:
        sandbox_script(lua, trigger.group(2), bot, trigger, extras)
    except Exception as e:
        bot.say('[lua] %r' % e)


def sandbox_script(lua, script, bot, trigger, extras):
    sandbox = lua.eval('require("sandbox_test")')
#    sandbox = lua.eval('require("sandbox")')
#    sandbox["allowed_require_names"]['selene'] = True
#    sandbox["allowed_require_names"]['selenep'] = True
#    sandbox["allowed_require_names"]['repr'] = True
#    script = ('function main(bot, trigger, extras) '
#              '  ' + script + '; end;')
#    result = sandbox.run(script)
    trigger = json.loads(json.dumps(trigger))
    wrapped = lua.eval("""
function(sandbox, bot, trigger, extras, script) 
  options={env={bot=bot, trigger=trigger, extras=extras}}
  return sandbox.protect(script, options)()
end""")
    return wrapped(sandbox, bot, trigger, extras, script)
#    if result is not True:
#        ok, res = result
#        raise lupa.LuaError(res)
#    safe_func = sandbox.env["main"]
#    return safe_func(bot, json.loads(json.dumps(trigger)), extras)


def setup_lua_paths(lua, lua_package_path):
    root = os.path.join(os.path.dirname(__file__), 'lua_modules')
    at_root = lambda *p: os.path.abspath(os.path.join(root, *p))
    default_path = "{root}/?.lua;{libs}/?.lua;{selene}/?.lua".format(
        root=at_root(),
        libs=at_root('libs'),
        selene=at_root('selene')
    )
    if lua_package_path:
        packages_path = ";".join([default_path, lua_package_path])
    else:
        packages_path = default_path

    lua.execute("""
package.path = "{packages_path};" .. package.path
    """.format(packages_path=packages_path))

