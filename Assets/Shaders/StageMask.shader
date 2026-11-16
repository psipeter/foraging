// Writes depth and no colour: a ranking stage draws it as a flat plane at its disc's surface height before its bushes, so the half of each bush that is buried in the disc
// (and would stick out through the disc's thin underside, since no terrain hides it) fails the depth test. Invisible itself.
Shader "Foraging/StageMask"
{
    SubShader
    {
        Tags
        {
            "RenderType"="Opaque"
            "Queue"="Geometry-10"
            "RenderPipeline"="UniversalPipeline"
        }

        Pass
        {
            Name "StageMask"
            Tags { "LightMode"="UniversalForward" }

            ColorMask 0
            ZWrite On
            ZTest LEqual
            Cull Off

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
            };

            struct Varyings
            {
                float4 positionHCS : SV_POSITION;
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                o.positionHCS = TransformObjectToHClip(v.positionOS.xyz);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                return 0;
            }
            ENDHLSL
        }
    }
}
