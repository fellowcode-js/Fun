package com.xon.studio;

import android.app.Activity;
import android.content.ContentValues;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;

import androidx.webkit.WebViewAssetLoader;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import org.json.JSONObject;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.HashMap;
import java.util.Map;

/** XON Studio: the bundled web app in a WebView. Everything runs on the phone unless you turn on the API brain; otherwise the only network use is the
 *  one-time download of the model weights from Hugging Face. */
public class MainActivity extends Activity {
    private static final String HOST = "appassets.androidplatform.net";
    private WebView web;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        web = new WebView(this);
        setContentView(web);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(false);
        s.setTextZoom(100);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setCacheMode(WebSettings.LOAD_DEFAULT);
        if (Build.VERSION.SDK_INT >= 26) web.setRendererPriorityPolicy(WebView.RENDERER_PRIORITY_IMPORTANT, false);

        final WebViewAssetLoader loader = new WebViewAssetLoader.Builder()
                .setDomain(HOST)
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .build();
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest req) {
                Uri u = req.getUrl();
                WebResourceResponse r = loader.shouldInterceptRequest(u);
                if (r == null) return null;  // network (model download): let WebView handle it
                String p = u.getPath() == null ? "" : u.getPath();
                String mime = p.endsWith(".mjs") || p.endsWith(".js") ? "text/javascript"
                        : p.endsWith(".wasm") ? "application/wasm" : p.endsWith(".json") ? "application/json"
                        : p.endsWith(".svg") ? "image/svg+xml" : p.endsWith(".html") ? "text/html"
                        : p.endsWith(".zip") ? "application/zip" : r.getMimeType();
                Map<String, String> h = new HashMap<>();
                if (r.getResponseHeaders() != null) h.putAll(r.getResponseHeaders());
                // Cross-origin isolation: lets the model use several CPU cores (SharedArrayBuffer threads).
                h.put("Cross-Origin-Opener-Policy", "same-origin");
                h.put("Cross-Origin-Embedder-Policy", "require-corp");
                h.put("Cross-Origin-Resource-Policy", "same-origin");
                h.put("Cache-Control", "no-cache");
                return new WebResourceResponse(mime, mime.startsWith("text/") || mime.endsWith("json") ? "utf-8" : null,
                        200, "OK", h, r.getData());
            }
        });
        web.addJavascriptInterface(new Bridge(), "XONAndroid");
        if (state != null) web.restoreState(state);
        else web.loadUrl("https://" + HOST + "/assets/index.html");
    }

    @Override protected void onSaveInstanceState(Bundle out) { super.onSaveInstanceState(out); web.saveState(out); }

    @Override
    public void onBackPressed() {
        if (web.canGoBack()) web.goBack(); else super.onBackPressed();
    }

    @Override protected void onDestroy() { if (web != null) web.destroy(); super.onDestroy(); }

    /** API brain requests (Ollama / OpenAI-compatible). Done natively so http:// servers on your Wi-Fi work
     *  without CORS or mixed-content limits. Runs off the UI thread; the answer comes back via window.__xonHttp. */
    class Net {
        @JavascriptInterface
        public void http(final int id, final String method, final String url, final String headers, final String body) {
            new Thread(() -> {
                int status = 0; String out;
                try {
                    HttpURLConnection c = (HttpURLConnection) new URL(url).openConnection();
                    c.setRequestMethod(method); c.setConnectTimeout(8000); c.setReadTimeout(300000);
                    c.setRequestProperty("Content-Type", "application/json");
                    JSONObject h = new JSONObject(headers == null || headers.isEmpty() ? "{}" : headers);
                    for (java.util.Iterator<String> it = h.keys(); it.hasNext(); ) { String k = it.next(); c.setRequestProperty(k, h.getString(k)); }
                    if (body != null && !body.isEmpty()) { c.setDoOutput(true); try (OutputStream o = c.getOutputStream()) { o.write(body.getBytes("UTF-8")); } }
                    status = c.getResponseCode();
                    InputStream in = status >= 400 ? c.getErrorStream() : c.getInputStream();
                    ByteArrayOutputStream buf = new ByteArrayOutputStream(); byte[] b = new byte[16384]; int n;
                    if (in != null) while ((n = in.read(b)) > 0) buf.write(b, 0, n);
                    out = buf.toString("UTF-8");
                } catch (Exception e) { status = 0; out = String.valueOf(e.getMessage()); }
                final String js = "window.__xonHttp(" + id + "," + status + "," + JSONObject.quote(out) + ")";
                runOnUiThread(() -> web.evaluateJavascript(js, null));
            }).start();
        }
    }

    /** Saves files the app makes (animation GIFs) into the phone's Downloads folder. */
    class Bridge extends Net {
        @JavascriptInterface
        public boolean saveFile(String name, String base64, String mime) {
            try {
                byte[] data = Base64.decode(base64, Base64.DEFAULT);
                if (Build.VERSION.SDK_INT >= 29) {
                    ContentValues v = new ContentValues();
                    v.put(MediaStore.Downloads.DISPLAY_NAME, name);
                    v.put(MediaStore.Downloads.MIME_TYPE, mime);
                    Uri uri = getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, v);
                    try (OutputStream o = getContentResolver().openOutputStream(uri)) { o.write(data); }
                } else {
                    File dir = getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
                    try (OutputStream o = new FileOutputStream(new File(dir, name))) { o.write(data); }
                }
                runOnUiThread(() -> Toast.makeText(MainActivity.this, "Saved to Downloads: " + name, Toast.LENGTH_SHORT).show());
                return true;
            } catch (Exception e) {
                return false;
            }
        }
    }
}
