// Minimal JSON value, parser and serializer. No dependencies.
#pragma once
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace strata {

struct Json {
    enum Type { Null, Bool, Num, Str, Arr, Obj };
    Type t = Null;
    bool b = false;
    double n = 0;
    std::string s;
    std::vector<Json> a;
    std::vector<std::pair<std::string, Json>> o;

    Json() {}
    Json(bool v) : t(Bool), b(v) {}
    Json(int v) : t(Num), n(v) {}
    Json(unsigned v) : t(Num), n(v) {}
    Json(long v) : t(Num), n((double)v) {}
    Json(long long v) : t(Num), n((double)v) {}
    Json(double v) : t(Num), n(v) {}
    Json(const char* v) : t(Str), s(v) {}
    Json(const std::string& v) : t(Str), s(v) {}

    static Json array() { Json j; j.t = Arr; return j; }
    static Json object() { Json j; j.t = Obj; return j; }

    bool isNum() const { return t == Num; }
    bool isStr() const { return t == Str; }
    bool isObj() const { return t == Obj; }
    bool isArr() const { return t == Arr; }

    const Json* find(const std::string& k) const {
        for (auto& kv : o) if (kv.first == k) return &kv.second;
        return nullptr;
    }
    void set(const std::string& k, Json v) {
        t = Obj;
        for (auto& kv : o) if (kv.first == k) { kv.second = std::move(v); return; }
        o.emplace_back(k, std::move(v));
    }
    void push(Json v) { t = Arr; a.push_back(std::move(v)); }

    // ---- serialization ----
    static void num(std::string& out, double v) {
        if (!std::isfinite(v)) { out += "null"; return; }
        char buf[40];
        for (int p = 6; p <= 17; p++) {
            snprintf(buf, sizeof buf, "%.*g", p, v);
            if (strtod(buf, nullptr) == v) break;
        }
        out += buf;
    }
    static void str(std::string& out, const std::string& v) {
        out += '"';
        for (unsigned char c : v) {
            switch (c) {
                case '"': out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                default:
                    if (c < 0x20) { char b[8]; snprintf(b, sizeof b, "\\u%04x", c); out += b; }
                    else out += (char)c;
            }
        }
        out += '"';
    }
    void dump(std::string& out, int indent, int depth) const {
        auto nl = [&](int d) { if (indent >= 0) { out += '\n'; out.append((size_t)d * indent, ' '); } };
        switch (t) {
            case Null: out += "null"; break;
            case Bool: out += b ? "true" : "false"; break;
            case Num: num(out, n); break;
            case Str: str(out, s); break;
            case Arr:
                if (a.empty()) { out += "[]"; break; }
                out += '[';
                for (size_t i = 0; i < a.size(); i++) {
                    if (i) out += ',';
                    nl(depth + 1);
                    a[i].dump(out, indent, depth + 1);
                }
                nl(depth);
                out += ']';
                break;
            case Obj:
                if (o.empty()) { out += "{}"; break; }
                out += '{';
                for (size_t i = 0; i < o.size(); i++) {
                    if (i) out += ',';
                    nl(depth + 1);
                    str(out, o[i].first);
                    out += indent >= 0 ? ": " : ":";
                    o[i].second.dump(out, indent, depth + 1);
                }
                nl(depth);
                out += '}';
                break;
        }
    }
    std::string dump(int indent = -1) const { std::string s; dump(s, indent, 0); return s; }

    // ---- parsing ----
    static Json parse(const std::string& text) {
        size_t i = 0;
        Json v = parseValue(text, i, 0);
        skip(text, i);
        if (i != text.size()) throw std::runtime_error("Unexpected text after JSON value");
        return v;
    }

private:
    static void skip(const std::string& s, size_t& i) {
        while (i < s.size() && (s[i] == ' ' || s[i] == '\n' || s[i] == '\r' || s[i] == '\t')) i++;
    }
    static void utf8(std::string& out, unsigned cp) {
        if (cp < 0x80) out += (char)cp;
        else if (cp < 0x800) { out += (char)(0xC0 | (cp >> 6)); out += (char)(0x80 | (cp & 63)); }
        else if (cp < 0x10000) { out += (char)(0xE0 | (cp >> 12)); out += (char)(0x80 | ((cp >> 6) & 63)); out += (char)(0x80 | (cp & 63)); }
        else { out += (char)(0xF0 | (cp >> 18)); out += (char)(0x80 | ((cp >> 12) & 63)); out += (char)(0x80 | ((cp >> 6) & 63)); out += (char)(0x80 | (cp & 63)); }
    }
    static unsigned hex4(const std::string& s, size_t& i) {
        if (i + 4 > s.size()) throw std::runtime_error("Bad \\u escape");
        unsigned v = 0;
        for (int k = 0; k < 4; k++) {
            char c = s[i++];
            v <<= 4;
            if (c >= '0' && c <= '9') v |= c - '0';
            else if (c >= 'a' && c <= 'f') v |= c - 'a' + 10;
            else if (c >= 'A' && c <= 'F') v |= c - 'A' + 10;
            else throw std::runtime_error("Bad \\u escape");
        }
        return v;
    }
    static std::string parseString(const std::string& s, size_t& i) {
        std::string out;
        i++;  // opening quote
        while (true) {
            if (i >= s.size()) throw std::runtime_error("Unterminated string");
            char c = s[i++];
            if (c == '"') break;
            if (c != '\\') { out += c; continue; }
            if (i >= s.size()) throw std::runtime_error("Bad escape");
            char e = s[i++];
            switch (e) {
                case '"': out += '"'; break;
                case '\\': out += '\\'; break;
                case '/': out += '/'; break;
                case 'b': out += '\b'; break;
                case 'f': out += '\f'; break;
                case 'n': out += '\n'; break;
                case 'r': out += '\r'; break;
                case 't': out += '\t'; break;
                case 'u': {
                    unsigned cp = hex4(s, i);
                    if (cp >= 0xD800 && cp < 0xDC00 && i + 1 < s.size() && s[i] == '\\' && s[i + 1] == 'u') {
                        i += 2;
                        unsigned lo = hex4(s, i);
                        cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                    }
                    utf8(out, cp);
                    break;
                }
                default: throw std::runtime_error("Bad escape");
            }
        }
        return out;
    }
    static Json parseValue(const std::string& s, size_t& i, int depth) {
        if (depth > 64) throw std::runtime_error("JSON nested too deeply");
        skip(s, i);
        if (i >= s.size()) throw std::runtime_error("Unexpected end of JSON");
        char c = s[i];
        if (c == '{') {
            Json j = object();
            i++;
            skip(s, i);
            if (i < s.size() && s[i] == '}') { i++; return j; }
            while (true) {
                skip(s, i);
                if (i >= s.size() || s[i] != '"') throw std::runtime_error("Expected a property name");
                std::string k = parseString(s, i);
                skip(s, i);
                if (i >= s.size() || s[i] != ':') throw std::runtime_error("Expected ':'");
                i++;
                j.set(k, parseValue(s, i, depth + 1));
                skip(s, i);
                if (i < s.size() && s[i] == ',') { i++; continue; }
                if (i < s.size() && s[i] == '}') { i++; break; }
                throw std::runtime_error("Expected ',' or '}'");
            }
            return j;
        }
        if (c == '[') {
            Json j = array();
            i++;
            skip(s, i);
            if (i < s.size() && s[i] == ']') { i++; return j; }
            while (true) {
                j.a.push_back(parseValue(s, i, depth + 1));
                skip(s, i);
                if (i < s.size() && s[i] == ',') { i++; continue; }
                if (i < s.size() && s[i] == ']') { i++; break; }
                throw std::runtime_error("Expected ',' or ']'");
            }
            return j;
        }
        if (c == '"') return Json(parseString(s, i));
        if (s.compare(i, 4, "true") == 0) { i += 4; return Json(true); }
        if (s.compare(i, 5, "false") == 0) { i += 5; return Json(false); }
        if (s.compare(i, 4, "null") == 0) { i += 4; return Json(); }
        const char* st = s.c_str() + i;
        char* end = nullptr;
        double v = strtod(st, &end);
        if (end == st) throw std::runtime_error("Unexpected character in JSON");
        i += (size_t)(end - st);
        return Json(v);
    }
};

}  // namespace strata
