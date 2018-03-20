from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_session import Session
from passlib.apps import custom_app_context as pwd_context
from tempfile import mkdtemp

from helpers import *

# configure application
app = Flask(__name__)

# ensure responses aren't cached
if app.config["DEBUG"]:
    @app.after_request
    def after_request(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Expires"] = 0
        response.headers["Pragma"] = "no-cache"
        return response

# custom filter
app.jinja_env.filters["usd"] = usd

# configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

@app.route("/")
@login_required
def index():
    """Page showing active transactions."""
    
    # get user attributes
    user = db.execute("SELECT * FROM users WHERE id = :session_id", session_id=session["user_id"])[0]
    
    transactions = db.execute("SELECT * FROM transactions WHERE user_id = :session_id", session_id=session["user_id"])
    
    # calculate relevant values
    for transaction in transactions:
        transaction["current_price"] = lookup(transaction["symbol"])["price"]
        transaction["total_price"] = usd(transaction["current_price"] * transaction["number"])
        transaction["current_price"] = usd(transaction["current_price"])
    
    # calculate total value of cash and stocks    
    try:
        equity = float(db.execute('SELECT SUM(price * number) FROM transactions WHERE user_id=:session_id', session_id=session["user_id"])[0]["SUM(price * number)"]) + float(user["cash"])
        equity = usd(equity)
    
    except TypeError:
        equity = usd(user["cash"])
        
    user["cash"] = usd(user["cash"])
    
    return render_template("index.html", user=user, transactions=transactions, equity=equity)

@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock."""
    if request.method == "POST":
        # checking all entered values are sensible
        if not request.form.get("symbol") or not request.form.get("shares"):
            return apology("Please enter both", "Fields!")
        
        quote = lookup(request.form.get("symbol"))
        
        # check if stock symbol exists
        if quote == None:
            return apology("Error Stock04:", "Stock Not Found")
            
        user = db.execute("SELECT * FROM users WHERE id = :session_id", session_id=session["user_id"])[0]
        existing = db.execute("SELECT * FROM transactions WHERE user_id = :session_id AND symbol = :symbol", session_id=user["id"], symbol=quote["symbol"])
        
        symbol = quote["symbol"]
        name = quote["name"]
        price = quote["price"]
        number = int(request.form.get("shares"))
        total_price = number * price
        new_cash = user["cash"] - total_price
        
        if total_price > user["cash"]:
            return apology("Don't touch what", "You Cannot Afford!")
        
        db.execute('INSERT INTO history ("user_id", "symbol", "name", "number", "price") \
        VALUES(:user_id, :symbol, :name, :number, :price)', user_id=user["id"], symbol=symbol, name=name, number=number, price=price)
        
        if len(existing) == 1:
            existing = existing[0]
            number += int(existing["number"])
            mean_price = ((float(existing["price"]) * float(existing["number"])) + total_price) / number
                
            db.execute('UPDATE transactions SET number = :number WHERE user_id = :user_id AND symbol = :symbol', number=number, user_id=user["id"], symbol=symbol)
            db.execute('UPDATE transactions SET price = :mean_price WHERE user_id = :user_id AND symbol = :symbol', mean_price=mean_price, user_id=user["id"], symbol=symbol)
        
        else:
            db.execute('INSERT INTO transactions ("user_id", "symbol", "name", "number", "price") \
            VALUES(:user_id, :symbol, :name, :number, :price)', user_id=user["id"], symbol=symbol, name=name, number=number, price=price)
        
        db.execute('UPDATE users SET cash = :new_cash WHERE id = :user_id', new_cash=new_cash, user_id=user["id"])
        
        return render_template("buy.html")
        
    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    
    """Show history of transactions."""
    
    # fetching history of transactions from database.
    history = db.execute("SELECT * FROM history WHERE user_id = :session_id", session_id=session["user_id"])
    
    # changing boolean value to string for viewing in table
    for transaction in history:
        # calculate total value of stock
        transaction["total_price"] = usd(transaction["price"] * int(transaction["number"]))
        transaction["price"] = usd(transaction["price"])
    
    return render_template("history.html", history=history)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in."""

    # forget any user_id
    session.clear()

    # if user reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")

        # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")

        # remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # redirect user to home page
        return redirect(url_for("index"))

    # else if user reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")

@app.route("/logout")
def logout():
    """Log user out."""

    # forget any user_id
    session.clear()

    # redirect user to login form
    return redirect(url_for("login"))

@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock(s) quote."""
    if request.method == "POST":
        if not request.form.get("symbol"):
            return apology("Please search for", "Something :/")
        
        # separate different symbols inputted by user, separated by comma
        query = request.form.get("symbol").replace(" ", "").split(",")
        
        # fetching quote if it exists using lookup function (from helpers.py)
        quotes = []
        no_quotes = []
        for q in query:
            if lookup(q) != None:
                quotes.append(lookup(q))
                
            else:
                # storing symbols that have invalid lookup returns
                no_quotes.append(str(q))
        
        return render_template("quoted.html", quotes=quotes, no_quotes=no_quotes)
    
    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user."""
    if request.method == "POST":
         # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")
            
        # ensure password entered again.
        elif not request.form.get("confirm_pass") or request.form.get("password") != request.form.get("confirm_pass"):
            return apology("Passwords", "DO NOT MATCH!")
        
        # check if username already taken
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))
        
        if len(rows) != 0:
            return apology("Account name taken already", "Sozzz!")
        
        # hash and store password in database
        hashed = pwd_context.encrypt(request.form.get("password"))
        db.execute("INSERT INTO users (username, hash) VALUES(:username, :hashed)", username=request.form.get("username"), hashed=hashed)
        
        return redirect(url_for("login"))
        
    else:
        return render_template("register.html")
    
@app.route("/unregister", methods=["GET", "POST"])
def unregister():
    """Unregisters an existing user"""
    if request.method == "POST":
         # ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username")

        # ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password")
            
        # ensure password entered correctly again.
        elif request.form.get("password") != request.form.get("confirm_pass"):
            return apology("Passwords", "DO NOT MATCH!")
        
         # query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username"))

        # ensure username exists and password is correct
        if len(rows) != 1 or not pwd_context.verify(request.form.get("password"), rows[0]["hash"]):
            return apology("invalid username and/or password")
            
        # delete transactions and history from databases.
        user = db.execute("SELECT * FROM users WHERE id = :session_id", session_id=session["user_id"])[0]
        db.execute("DELETE FROM transactions WHERE user_id = :session_id", session_id = user["id"])
        db.execute("DELETE FROM history WHERE user_id = :session_id", session_id = user["id"])
        
        # delete from database
        session.clear()
        db.execute("DELETE FROM users WHERE username = :username", username=request.form.get("username"))
        
        
        return redirect(url_for("login"))
        
    elif request.method == "GET":
        return render_template("unregister.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock."""
    if request.method == "POST":
        # checking all entered values are sensible
        if not request.form.get("symbol") or not request.form.get("shares"):
            return apology("Please enter both", "Fields!")
        
        quote = lookup(request.form.get("symbol"))
        
        # check if stock symbol exists
        if quote == None:
            return apology("Error Stock04:", "Stock Not Found")
            
        # user details
        user = db.execute("SELECT * FROM users WHERE id = :session_id", session_id=session["user_id"])[0]
        # finding existing transaction in user's history.
        existing = db.execute("SELECT * FROM transactions WHERE user_id = :session_id AND symbol = :symbol", session_id=user["id"], symbol=quote["symbol"])
        
        # sanity checks - does user have the stock to sell?
        if len(existing) < 1:
            return apology("You do not own", "This Stock!")
            
        elif len(existing) > 1:
            return apology("Internal DataBase error!", "I'm sorry :/")
            
        existing = existing[0]
        symbol = quote["symbol"]
        name = quote["name"]
        price = quote["price"]
        number = int(request.form.get("shares"))
        
        # can't sell more than you buy here.
        if int(existing["number"]) < number:
            return apology("Short selling", "Not supported :/")
        
        total_price = number * price
        new_cash = user["cash"] + total_price
        
        if existing["number"] > number:
            number -= existing["number"]
            mean_price = ((existing["price"] * existing["number"]) - total_price) / number
            db.execute('UPDATE transaction SET number = :number WHERE user_id = :user_id AND symbol = :symbol', number=number, user_id=user["id"], symbol=symbol)
            db.execute('UPDATE transaction SET price = :mean_price WHERE user_id = :user_id AND symbol = :symbol', mean_price=mean_price, symbol=symbol)
            
        elif existing["number"] == number:
            db.execute('DELETE FROM transactions WHERE user_id = :session_id AND symbol = :symbol', session_id=user["id"], symbol=symbol)
            
        db.execute('UPDATE users SET cash = :new_cash WHERE id = :session_id', new_cash=new_cash, session_id=user["id"])
        
        db.execute('INSERT INTO history ("user_id", "symbol", "name", "number", "price") \
                    VALUES(:user_id, :symbol, :name, :number, :price)', user_id=user["id"], symbol=symbol, name=name, number=-number, price=price)
        
        return render_template("sell.html")
        
    else:
        return render_template("sell.html")
    