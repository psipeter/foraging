// Clock-style progress ring drawn on a camera-facing quad. _Fill is the remaining fraction: the bright arc is
// erased clockwise from 12 o'clock as the fill drops; the erased part shows as a faint track.
Shader "Foraging/HarvestRing"
{
    Properties
    {
        _Color ("Color", Color) = (1, 0.9, 0.6, 1)
        _Fill ("Fill", Range(0, 1)) = 1
        _InnerRadius ("Inner Radius", Range(0, 0.5)) = 0.36
        _OuterRadius ("Outer Radius", Range(0, 0.5)) = 0.48
        _TrackAlpha ("Track Alpha", Range(0, 1)) = 0.25
    }

    SubShader
    {
        Tags
        {
            "RenderType"="Transparent"
            "Queue"="Transparent+10"
            "RenderPipeline"="UniversalPipeline"
        }

        Pass
        {
            Name "Ring"
            Tags { "LightMode"="UniversalForward" }

            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            Cull Off

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _Color;
                float _Fill;
                float _InnerRadius;
                float _OuterRadius;
                float _TrackAlpha;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 uv         : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionHCS : SV_POSITION;
                float2 uv          : TEXCOORD0;
                float  fogCoord    : TEXCOORD1;
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                VertexPositionInputs pos = GetVertexPositionInputs(v.positionOS.xyz);
                o.positionHCS = pos.positionCS;
                o.uv = v.uv;
                o.fogCoord = ComputeFogFactor(pos.positionCS.z);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                float2 p = i.uv - 0.5;
                float r = length(p);
                float aa = max(fwidth(r), 0.0005);
                float ring = smoothstep(_InnerRadius - aa, _InnerRadius + aa, r) *
                             (1.0 - smoothstep(_OuterRadius - aa, _OuterRadius + aa, r));

                // 0 at 12 o'clock, increasing clockwise, in [0, 1).
                float t = frac(atan2(p.x, p.y) / 6.2831853 + 1.0);
                float edge = max(fwidth(t), 0.002);
                float remaining = smoothstep(1.0 - _Fill - edge, 1.0 - _Fill + edge, t);
                remaining = _Fill >= 0.999 ? 1.0 : remaining;

                float alpha = ring * lerp(_TrackAlpha, 1.0, remaining);
                half3 color = MixFog(_Color.rgb, i.fogCoord);
                return half4(color, alpha);
            }
            ENDHLSL
        }
    }
}
