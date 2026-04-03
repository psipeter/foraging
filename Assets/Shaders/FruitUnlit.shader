Shader "Foraging/FruitUnlit"
{
    Properties
    {
        _Color ("Color", Color) = (1,1,1,1)
        _MainTex ("Main Texture", 2D) = "white" {}
        _NormalMap ("Normal Map", 2D) = "bump" {}
        _Tiling ("Tiling", Float) = 4.0
        _NormalStrength ("Normal Strength", Float) = 0.5
        _ColorPreservation ("Color Preservation", Range(0,1)) = 0.5
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
            Name "FruitLit"
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

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            TEXTURE2D(_MainTex);
            SAMPLER(sampler_MainTex);
            TEXTURE2D(_NormalMap);
            SAMPLER(sampler_NormalMap);

            CBUFFER_START(UnityPerMaterial)
                float4 _Color;
                float _Tiling;
                float _NormalStrength;
                float _ColorPreservation;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS   : NORMAL;
                float4 tangentOS  : TANGENT;
                float2 uv         : TEXCOORD0;
            };

            struct Varyings
            {
                float4 positionHCS : SV_POSITION;
                float3 positionWS  : TEXCOORD0;
                float3 normalWS    : TEXCOORD1;
                float3 tangentWS   : TEXCOORD2;
                float3 bitangentWS : TEXCOORD3;
                float4 shadowCoord : TEXCOORD4;
                float2 uv          : TEXCOORD5;
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                VertexPositionInputs posInputs = GetVertexPositionInputs(v.positionOS.xyz);
                VertexNormalInputs normInputs = GetVertexNormalInputs(v.normalOS, v.tangentOS);

                o.positionHCS = posInputs.positionCS;
                o.positionWS = posInputs.positionWS;
                o.normalWS = normInputs.normalWS;
                o.tangentWS = normInputs.tangentWS;
                o.bitangentWS = normInputs.bitangentWS;
                o.shadowCoord = TransformWorldToShadowCoord(posInputs.positionWS);
                o.uv = v.uv * _Tiling;
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                half3 albedo = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, i.uv).rgb * (half3)_Color.rgb;

                half3 tangentNormal = UnpackNormal(SAMPLE_TEXTURE2D(_NormalMap, sampler_NormalMap, i.uv));
                tangentNormal = lerp(half3(0, 0, 1), tangentNormal, (half)_NormalStrength);

                float3x3 TBN = float3x3(i.tangentWS, i.bitangentWS, i.normalWS);
                float3 normalWS = normalize(mul(tangentNormal, TBN));

                Light mainLight = GetMainLight(i.shadowCoord);
                float3 lightDir = normalize(mainLight.direction);
                float3 viewDir = normalize(GetWorldSpaceViewDir(i.positionWS));

                half NdotL = saturate(dot((half3)normalWS, (half3)lightDir));
                half diffuse = 0.3h + 0.7h * NdotL * mainLight.shadowAttenuation;

                float3 halfDir = normalize(lightDir + viewDir);
                half specTerm = pow(saturate(dot((half3)normalWS, (half3)halfDir)), 64.0h) * 0.5h * mainLight.shadowAttenuation;
                half3 specular = specTerm * (half3)mainLight.color.rgb;

                half3 ambient = (half3)unity_AmbientSky.rgb * 2.5h;
                ambient.r = max(ambient.r, 0.35h);
                ambient.g = max(ambient.g, 0.35h);
                ambient.b = max(ambient.b, 0.35h);

                half3 fullyLit = albedo * diffuse + specular;
                half3 colorPreserved = (half3)_Color.rgb * ambient;
                half3 lit = lerp(fullyLit, colorPreserved, (half)_ColorPreservation);
                return half4(lit, _Color.a);
            }
            ENDHLSL
        }
    }
}
