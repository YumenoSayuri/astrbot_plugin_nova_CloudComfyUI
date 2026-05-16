export default {
  async fetch(request) {
    const url = new URL(request.url);

    if (request.method === "OPTIONS") {
      return new Response(null, {
        status: 204,
        headers: corsHeaders(),
      });
    }

    if (url.pathname === "/health") {
      return jsonResponse(
        {
          success: true,
          service: "nova-mengyudraw-cf-worker-proxy",
          upstream: "https://sd.exacg.cc",
        },
        200,
      );
    }

    if (url.pathname !== "/api/v1/generate_image") {
      return jsonResponse(
        {
          error: "Not Found",
          message: "Only /api/v1/generate_image is supported",
        },
        404,
      );
    }

    if (request.method !== "POST") {
      return jsonResponse(
        {
          error: "Method Not Allowed",
          message: "Use POST /api/v1/generate_image",
        },
        405,
      );
    }

    try {
      const rawBody = await request.text();
      const authHeader = request.headers.get("Authorization") || "";
      const contentType = request.headers.get("Content-Type") || "application/json";

      const upstreamResp = await fetch("https://sd.exacg.cc/api/v1/generate_image", {
        method: "POST",
        headers: {
          "Authorization": authHeader,
          "Content-Type": contentType,
          "User-Agent": "Mozilla/5.0 (compatible; NovaMengyuDrawWorker/1.3.0)",
          "Accept": "application/json, text/plain, */*",
        },
        body: rawBody,
      });

      const upstreamText = await upstreamResp.text();
      const upstreamType = upstreamResp.headers.get("content-type") || "application/json";

      return new Response(upstreamText, {
        status: upstreamResp.status,
        headers: {
          ...corsHeaders(),
          "Content-Type": upstreamType,
          "Cache-Control": "no-store",
        },
      });
    } catch (error) {
      return jsonResponse(
        {
          error: "Worker Proxy Error",
          message: error instanceof Error ? error.message : String(error),
        },
        500,
      );
    }
  },
};

function corsHeaders() {
  return {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "POST, OPTIONS, GET",
    "Access-Control-Allow-Headers": "Content-Type, Authorization",
  };
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data, null, 2), {
    status,
    headers: {
      ...corsHeaders(),
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
    },
  });
}