from flask import Flask, redirect, request

app = Flask(__name__)

@app.route("/download")
def download():
    url = request.args.get("url")
    if url:
        return redirect(url)
    return "No URL provided", 400

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
