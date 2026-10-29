using System.Globalization;
using System.Text;

// Just enough JSON writing for the log rows (JsonUtility cannot write a dictionary, and these are built per event).
public static class Json
{
    // A value already formatted as JSON (a nested object), passed through unchanged.
    public readonly struct Raw
    {
        public readonly string Text;
        public Raw(string text) { Text = text; }
    }

    public static string Quote(string s)
    {
        if (s == null)
        {
            return "null";
        }

        var sb = new StringBuilder(s.Length + 2).Append('"');
        foreach (char c in s)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                default:
                    if (c < 0x20)
                    {
                        sb.Append("\\u").Append(((int)c).ToString("x4"));
                    }
                    else
                    {
                        sb.Append(c);
                    }

                    break;
            }
        }

        return sb.Append('"').ToString();
    }

    // null, bool, int, long, float (4 decimals at most), double (round trip), string or Raw; NaN and infinities are null.
    public static string Value(object v)
    {
        switch (v)
        {
            case null: return "null";
            case bool b: return b ? "true" : "false";
            case int i: return i.ToString(CultureInfo.InvariantCulture);
            case long l: return l.ToString(CultureInfo.InvariantCulture);
            case float f: return float.IsNaN(f) || float.IsInfinity(f) ? "null" : f.ToString("0.####", CultureInfo.InvariantCulture);
            case double d: return double.IsNaN(d) || double.IsInfinity(d) ? "null" : d.ToString("R", CultureInfo.InvariantCulture);
            case string s: return Quote(s);
            case Raw r: return r.Text;
            default: return Quote(v.ToString());
        }
    }

    public static string Obj(params (string key, object value)[] fields)
    {
        var sb = new StringBuilder("{");
        for (int i = 0; i < fields.Length; i++)
        {
            if (i > 0)
            {
                sb.Append(',');
            }

            sb.Append(Quote(fields[i].key)).Append(':').Append(Value(fields[i].value));
        }

        return sb.Append('}').ToString();
    }
}
