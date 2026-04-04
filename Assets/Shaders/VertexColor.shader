Shader "Universal Render Pipeline/Unlit/VertexColor"
{
    Properties
    {
        _AridTex ("Arid Texture", 2D) = "white" {}
        _GrasslandTex ("Grassland Texture", 2D) = "white" {}
        _SwampTex ("Swamp Texture", 2D) = "white" {}
        _AridNormal ("Arid Normal", 2D) = "bump" {}
        _GrasslandNormal ("Grassland Normal", 2D) = "bump" {}
        _SwampNormal ("Swamp Normal", 2D) = "bump" {}
        _Tiling ("Texture Tiling", Float) = 8.0
        _NormalStrength ("Normal Strength", Float) = 0.8
    }

    SubShader
    {
        Tags
        {
            "RenderType"="Opaque"
            "Queue"="Geometry"
            "RenderPipeline"="UniversalPipeline"
        }

        Pass
        {
            Name "VertexColorShadowed"
            Tags { "LightMode"="UniversalForward" }

            ZWrite On
            Cull Back

            HLSLPROGRAM
            #pragma target 3.0

            #pragma vertex vert
            #pragma fragment frag

            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile _ _SHADOWS_SOFT
            #pragma multi_compile_fog

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            TEXTURE2D(_AridTex);       SAMPLER(sampler_AridTex);
            TEXTURE2D(_GrasslandTex);  SAMPLER(sampler_GrasslandTex);
            TEXTURE2D(_SwampTex);      SAMPLER(sampler_SwampTex);
            TEXTURE2D(_AridNormal);    SAMPLER(sampler_AridNormal);
            TEXTURE2D(_GrasslandNormal); SAMPLER(sampler_GrasslandNormal);
            TEXTURE2D(_SwampNormal);   SAMPLER(sampler_SwampNormal);

            CBUFFER_START(UnityPerMaterial)
                float _Tiling;
                float _NormalStrength;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float2 uv         : TEXCOORD0;
                float2 uv2        : TEXCOORD1;
                float3 normalOS   : NORMAL;
                float4 tangentOS  : TANGENT;
            };

            struct Varyings
            {
                float4 positionHCS : SV_POSITION;
                float3 positionWS  : TEXCOORD0;
                float2 uv          : TEXCOORD1;
                float  moisture    : TEXCOORD2;
                float3 normalWS    : TEXCOORD3;
                float3 tangentWS   : TEXCOORD4;
                float3 bitangentWS : TEXCOORD5;
                float  fogCoord    : TEXCOORD6;
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                VertexPositionInputs posInputs = GetVertexPositionInputs(v.positionOS.xyz);
                VertexNormalInputs normInputs = GetVertexNormalInputs(v.normalOS, v.tangentOS);
                o.positionHCS  = posInputs.positionCS;
                o.positionWS   = posInputs.positionWS;
                o.uv           = v.uv * _Tiling;
                o.moisture     = v.uv2.x;
                o.normalWS     = normInputs.normalWS;
                o.tangentWS    = normInputs.tangentWS;
                o.bitangentWS  = normInputs.bitangentWS;
                o.fogCoord     = ComputeFogFactor(o.positionHCS.z);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                float moisture = saturate(i.moisture);

                // Sample all three albedo textures
                half3 aridColor     = SAMPLE_TEXTURE2D(_AridTex,      sampler_AridTex,      i.uv).rgb;
                half3 grassColor    = SAMPLE_TEXTURE2D(_GrasslandTex, sampler_GrasslandTex, i.uv).rgb;
                half3 swampColor    = SAMPLE_TEXTURE2D(_SwampTex,     sampler_SwampTex,     i.uv).rgb;

                // Two-segment blend: 0 = arid, 0.5 = grassland, 1 = swamp
                half3 texColor;
                if (moisture < 0.5)
                    texColor = lerp(aridColor, grassColor, moisture * 2.0);
                else
                    texColor = lerp(grassColor, swampColor, (moisture - 0.5) * 2.0);

                half3 albedo = texColor;

                // Sample and blend normal maps
                half3 aridNorm  = UnpackNormal(SAMPLE_TEXTURE2D(_AridNormal,      sampler_AridNormal,      i.uv));
                half3 grassNorm = UnpackNormal(SAMPLE_TEXTURE2D(_GrasslandNormal, sampler_GrasslandNormal, i.uv));
                half3 swampNorm = UnpackNormal(SAMPLE_TEXTURE2D(_SwampNormal,     sampler_SwampNormal,     i.uv));

                half3 blendedNorm;
                if (moisture < 0.5)
                    blendedNorm = lerp(aridNorm, grassNorm, moisture * 2.0);
                else
                    blendedNorm = lerp(grassNorm, swampNorm, (moisture - 0.5) * 2.0);

                blendedNorm = lerp(half3(0,0,1), blendedNorm, _NormalStrength);

                float3x3 TBN = float3x3(i.tangentWS, i.bitangentWS, i.normalWS);
                float3 normalWS = normalize(mul(blendedNorm, TBN));

                // Lighting
                float4 shadowCoord = TransformWorldToShadowCoord(i.positionWS);
                Light mainLight = GetMainLight(shadowCoord);
                half shadow = mainLight.shadowAttenuation;

                // Simple diffuse using blended normal
                half NdotL = saturate(dot(normalWS, mainLight.direction));
                half lighting = 0.15h + 0.85h * shadow * NdotL;

                half3 ambient = unity_AmbientSky.rgb;
                half4 color = half4(albedo * lighting + albedo * ambient * 0.3, 1.0h);
                color.rgb = MixFog(color.rgb, i.fogCoord);
                return color;
            }
            ENDHLSL
        }
    }
}
