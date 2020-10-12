# Skeleton API server for writing meatshields bots
see https://meatshields.com/createBotGuide.php for official documentation.

# Trying the nullbot
To play the nullbot, visit https://meatshields.com/playUserBot.php and select "null bot"

To register the nullbot for yourself, visit https://meatshields.com/addUpdateBot.php and add this URL: http://meatshields-nullbot.jewsforbacon.com:5000

# Installing Flask-Restful on Ubuntu 16.04
protip: remember to open port 5000 so the meatshields can talk to your bot.

protip: for production use, remember to add your bot to the OS startup scripts, e.g. https://linuxconfig.org/how-to-automatically-execute-shell-script-at-startup-boot-on-systemd-linux

```
pip3 install flask flask-restful
```

# Running the bot server
```shell
./run.sh
 * Serving Flask app "nullbot"
 * Forcing debug mode on
 * Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)
 * Restarting with stat
 * Debugger is active!
 * Debugger PIN: 215-502-141
```

# Testing the heartbeat interface
```shell
./test_heartbeat.sh
OK
```

# Testing the nextmove interface
```shell
./test_nextmove.sh
{
    "status": "success",
    "data": {
        "purchase": false,
        "end_turn": true,
        "move": false
    }
}
```

# Running the server simulator
This causes basicbot.py to play against itself. 

```shell
./sim.py
```

Note that pypy3 *is* supported and greatly speeds up simulation. To run, use `pypy3 sim.py`. On Mac, you can `brew install pypy3`. For silly reasons, numpy is used, so also run `pypy3 -m pip install numpy`.
