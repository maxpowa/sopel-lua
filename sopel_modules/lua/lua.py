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


class TriggerWrapper:
    def __init__(self, trigger):
        self._trigger = trigger


    def __getattr__(self, name):
        try:
            return getattr(self._trigger, name)
        except AttributeError as e:
            raise AttributeError("'Trigger' object has no attribute '%s'" % name)


class Extras:
    def str(self, obj):
        if not isinstance(obj, str):
            return self.dump_json(obj)
        return '%s' % obj

    def load_json(self, obj):
        return json.loads(obj)

    def dump_json(self, obj):
        return json.dumps(obj)


@module.commands('([\S]*)(.*)')
def listen_for_commands(bot, trigger):
    if trigger.sender.is_nick():
        return

    if not trigger.group(2):
        return

    commands = bot.db.get_channel_value(trigger.sender, 'commands')
    if not commands:
        return

    for command, script in commands.items():
        if command == trigger.group(2).lower().strip():
            run_untrusted_lua_script(bot, trigger, script)


@module.commands('def_cmd', 'define_cmd', 'define_command')
@module.require_privilege(module.OP)
@module.require_chanmsg('You must be in a channel to define a command')
def define_cmd(bot, trigger):
    """.define_cmd <name> <lua script> - Create a command based on the given lua script"""
    if not trigger.group(2):
        return bot.say(define_cmd.__doc__)

    commands = bot.db.get_channel_value(trigger.sender, 'commands')
    if not commands:
        commands = dict()

    command = trigger.group(3).lower().strip()
    script = trigger.group(2).replace(command, '', 1).strip()
    commands[command] = script
    bot.db.set_channel_value(trigger.sender, 'commands', commands)
    bot.say("Successfully created new command. You should now be able to run '%s' in %s" % (trigger.group(3), trigger.sender))


@module.commands('get_cmd', 'get_command')
@module.require_privilege(module.OP)
@module.require_chanmsg('You must be in a channel to use this command')
def get_cmd(bot, trigger):
    if not trigger.group(2):
        return bot.say(define_cmd.__doc__)

    commands = bot.db.get_channel_value(trigger.sender, 'commands')
    if not commands:
        commands = dict()

    command = trigger.group(3).lower().strip()
    if command in commands:
        return bot.reply(commands[command])

    bot.reply("'%s' does not exist" % command)


@module.commands('lua')
def lua_cmd(bot, trigger):
    script = trigger.group(2)
    run_untrusted_lua_script(bot, trigger, script)


def run_untrusted_lua_script(bot, trigger, script):
    extras = Extras()
    trigger = TriggerWrapper(trigger)

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
    _allowed_object_attrs[extras] = ['*']
    _allowed_object_attrs[trigger] = ['*']
    

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
        sandbox_script(lua, script, bot, trigger, extras)
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
    lua.execute("""
if not _G._selene then _G._selene = {} end
_G._selene.liveMode = false
_G._selene.doAutoload = true
require("selene")
    """)

