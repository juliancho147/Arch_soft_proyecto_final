package co.uniandes.taq.comun;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;

public final class Json {
    public static final ObjectMapper M = new ObjectMapper();
    private Json() {}

    public static String a(Object o) {
        try { return M.writeValueAsString(o); } catch (Exception e) { throw new RuntimeException(e); }
    }
    public static Map<String, Object> mapa(String s) {
        try { return M.readValue(s, new TypeReference<Map<String, Object>>() {}); } catch (Exception e) { throw new RuntimeException(e); }
    }
}
