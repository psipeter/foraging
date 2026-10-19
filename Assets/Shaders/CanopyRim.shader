// Additive fresnel rim drawn on a slightly enlarged copy of the canopy mesh (the canopy's own material is untouched).
// Two terms: a wide soft glow that grows as a bush is approached, and a thin crisp edge line for the selected bush.
Shader "Foraging/CanopyRim"
{
    Properties
    {
        _RimColor ("Rim Color", Color) = (1, 0.96, 0.82, 1)
        _SoftIntensity ("Soft Intensity", Float) = 0
        _SoftPower ("Soft Power", Float) = 2.5
        _CrispIntensity ("Crisp Intensity", Float) = 0
        _CrispPower ("Crisp Power", Float) = 8
    }

    SubShader
    {
        Tags
        {
            "RenderType"="Transparent"
            "Queue"="Transparent"
            "RenderPipeline"="UniversalPipeline"
        }

        Pass
        {
            Name "Rim"
            Tags { "LightMode"="UniversalForward" }

            Blend One One
            ZWrite Off
            Cull Back

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
                float4 _RimColor;
                float _SoftIntensity;
                float _SoftPower;
                float _CrispIntensity;
                float _CrispPower;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
            };

            struct Varyings
            {
                float4 positionHCS : SV_POSITION;
                float3 normalWS    : TEXCOORD0;
                float3 viewDirWS   : TEXCOORD1;
                float  fogCoord    : TEXCOORD2;
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                VertexPositionInputs pos = GetVertexPositionInputs(v.positionOS.xyz);
                o.positionHCS = pos.positionCS;
                o.normalWS    = TransformObjectToWorldNormal(v.normalOS);
                o.viewDirWS   = GetWorldSpaceViewDir(pos.positionWS);
                o.fogCoord    = ComputeFogFactor(pos.positionCS.z);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                float3 n = normalize(i.normalWS);
                float3 v = normalize(i.viewDirWS);
                float f = 1.0 - saturate(dot(n, v));

                float rim = pow(f, _SoftPower) * _SoftIntensity + pow(f, _CrispPower) * _CrispIntensity;
                half3 color = _RimColor.rgb * rim;
                color = MixFogColor(color, half3(0, 0, 0), i.fogCoord);   // additive: fog fades toward black
                return half4(color, 1.0h);
            }
            ENDHLSL
        }
    }
}
